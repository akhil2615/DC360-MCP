from __future__ import annotations

from datetime import datetime, timedelta
import logging
import os
import sys
import base64
import hashlib
import secrets
from threading import Thread
import http.server
import webbrowser
from urllib.parse import parse_qs, urlparse
from typing import Tuple

import requests
from rfc3986 import builder as uri_builder

logger = logging.getLogger(__name__)


class OAuthConfig:
    def __init__(self, client_id: str, client_secret: str, login_root: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.login_root = login_root
        self.redirect_uri = redirect_uri

    @classmethod
    def from_env(cls) -> "OAuthConfig":
        client_id = os.getenv("SF_CLIENT_ID")
        client_secret = os.getenv("SF_CLIENT_SECRET")
        login_root = os.getenv("SF_LOGIN_URL", "login.salesforce.com")
        redirect_uri = os.getenv("SF_CALLBACK_URL", "http://localhost:55556/Callback")

        missing = [name for name, val in {
            "SF_CLIENT_ID": client_id,
            "SF_CLIENT_SECRET": client_secret,
        }.items() if not val]
        if missing:
            print(f"Error: Missing required environment variables: {', '.join(missing)}")
            sys.exit(1)

        return cls(
            client_id=client_id,
            client_secret=client_secret,
            login_root=login_root,
            redirect_uri=redirect_uri,
        )


class _RequestHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        parts = urlparse(self.path)
        if parts.path.lower() != "/callback":
            self.send_error(404, "Not Found")
            return

        args = parse_qs(parts.query)
        self.server.oauth_result = args

        has_code = "code" in args
        body = f"Final Status: {has_code=}\nYou can close this window now".encode()
        self.send_response(200, "OK")
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        logger.debug(format, *args)


def _generate_pkce_pair() -> Tuple[str, str]:
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("utf-8").rstrip("=")
    challenge = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    code_challenge = base64.urlsafe_b64encode(challenge).decode("utf-8").rstrip("=")
    return code_verifier, code_challenge


class OAuthSession:
    def __init__(self, config: OAuthConfig):
        self.config = config

        # --- Salesforce (standard OAuth) credentials ---
        self.token: str | None = None
        self.exp: datetime | None = None
        self.instance_url: str | None = None

        # --- Data Cloud (c360a) credentials ---
        # Obtained by exchanging the SF token at /services/a360/token
        self.dc_token: str | None = None
        self.dc_exp: datetime | None = None
        self.dc_instance_url: str | None = None

    def _run_oauth_flow(self, scopes: list[str]):
        logger.info(f"Starting OAuth flow with scopes: {scopes}")
        login_url = f"https://{self.config.login_root}/services/oauth2/authorize"
        token_exchange_url = f"https://{self.config.login_root}/services/oauth2/token"
        redirect_uri = self.config.redirect_uri

        code_verifier, code_challenge = _generate_pkce_pair()

        browser_uri: str = (
            uri_builder.URIBuilder(path=login_url)
            .add_query_from({
                "client_id": self.config.client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": " ".join(scopes),
                "prompt": "login",
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            })
            .finalize()
            .unsplit()
        )

        parsed_redirect = urlparse(redirect_uri)
        port = parsed_redirect.port

        logger.debug(f"Starting OAuth callback server on localhost:{port}")
        server = http.server.HTTPServer(("localhost", port), _RequestHandler)
        server.allow_reuse_address = True
        t = Thread(target=server.handle_request, daemon=True)
        t.start()

        logger.info("Opening browser for OAuth authorization")
        webbrowser.open_new_tab(browser_uri)
        while t.is_alive():
            t.join(10)

        oauth_result_args = server.oauth_result

        if "code" not in oauth_result_args:
            error_msg = "OAuth authentication failed — no authorization code received"
            if "error" in oauth_result_args:
                error_msg += f". Error: {oauth_result_args['error'][0]}"
            if "error_description" in oauth_result_args:
                error_msg += f" — {oauth_result_args['error_description'][0]}"
            raise Exception(error_msg)

        code = oauth_result_args["code"][0]
        logger.info("Authorization code received, exchanging for access token")

        response = requests.post(
            token_exchange_url,
            {
                "grant_type": "authorization_code",
                "code": code,
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            },
            headers={"Accept": "application/json"},
        )

        logger.info(
            f"Token exchange: status={response.status_code}, "
            f"elapsed={response.elapsed.total_seconds():.2f}s"
        )
        if response.status_code >= 400:
            logger.error(f"Token exchange failed: {response.text}")
        response.raise_for_status()

        logger.info("Successfully obtained access token")
        return response.json()

    def ensure_access(self) -> str:
        if self.exp is not None and datetime.now() > self.exp:
            self.exp = None
            self.token = None
            # Invalidate DC token too — it was derived from the SF token
            self.dc_token = None
            self.dc_exp = None

        if self.token is None:
            auth_info = self._run_oauth_flow(
                ["api", "cdp_query_api", "cdp_profile_api", "cdp_ingest_api"]
            )
            self.token = auth_info["access_token"]
            self.exp = datetime.now() + timedelta(minutes=110)
            self.instance_url = auth_info["instance_url"]

        return self.token

    def get_token(self) -> str:
        return self.ensure_access()

    def get_instance_url(self) -> str:
        self.ensure_access()
        return self.instance_url

    # ------------------------------------------------------------------
    # Data Cloud (c360a) token — obtained by exchanging the SF token at
    # POST {instance_url}/services/a360/token
    # Returns a separate access_token and the c360a tenant URL.
    # ------------------------------------------------------------------

    def _exchange_for_dc_token(self) -> dict:
        """Exchange the Salesforce access token for a Data Cloud (c360a) token."""
        url = f"{self.instance_url}/services/a360/token"
        logger.info(f"Exchanging SF token for Data Cloud token at {url}")
        response = requests.post(
            url,
            data={
                "grant_type": "urn:salesforce:grant-type:external:cdp",
                "subject_token": self.token,
                "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=60,
        )
        logger.info(
            f"DC token exchange: status={response.status_code}, "
            f"elapsed={response.elapsed.total_seconds():.2f}s"
        )
        if response.status_code >= 400:
            logger.error(f"DC token exchange failed: {response.text}")
        response.raise_for_status()
        return response.json()

    def ensure_dc_access(self) -> str:
        """Ensure we have a valid Data Cloud token, refreshing if needed."""
        self.ensure_access()  # guarantee the SF token is fresh first

        if self.dc_exp is not None and datetime.now() > self.dc_exp:
            self.dc_token = None
            self.dc_exp = None

        if self.dc_token is None:
            dc_info = self._exchange_for_dc_token()
            self.dc_token = dc_info["access_token"]
            # DC tokens typically expire in 2 hours; use 110 min to be safe
            self.dc_exp = datetime.now() + timedelta(minutes=110)

            raw_url = dc_info.get("instance_url", self.instance_url)
            # Ensure scheme is present
            if raw_url and not raw_url.startswith("http"):
                raw_url = "https://" + raw_url
            # Strip any path component — the c360a URL must be scheme+host only.
            # Some orgs return e.g. "https://xxxx.c360a.salesforce.com/query"
            # and appending /api/v1/metadata/ would break the path.
            parsed = urlparse(raw_url)
            self.dc_instance_url = f"{parsed.scheme}://{parsed.netloc}"
            logger.info(f"Data Cloud tenant URL (normalised): {self.dc_instance_url}")

        return self.dc_token

    def get_dc_token(self) -> str:
        """Return the Data Cloud (c360a) access token."""
        return self.ensure_dc_access()

    def get_dc_instance_url(self) -> str:
        """Return the Data Cloud tenant URL (e.g. https://xxxx.c360a.salesforce.com)."""
        self.ensure_dc_access()
        return self.dc_instance_url
