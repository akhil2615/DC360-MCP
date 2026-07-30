from __future__ import annotations

import requests
from typing import Any, Dict, Optional

from oauth import OAuthSession
from .contracts import op_result

API_VERSION = "v63.0"


def _call_connect_api(
    oauth_session: OAuthSession,
    method: str,
    path: str,
    body: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not path.startswith("/services/"):
        raise ValueError("path must start with /services/")
    base = oauth_session.get_instance_url().rstrip("/")
    token = oauth_session.get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    response = requests.request(
        method=method.upper(),
        url=f"{base}{path}",
        headers=headers,
        json=body,
        params=params,
        timeout=90,
    )
    response.raise_for_status()
    if response.status_code == 204 or not response.text:
        return {}
    return response.json()


def safe_mutation(
    oauth_session: OAuthSession,
    action: str,
    method: str,
    path: str,
    body: Optional[Dict[str, Any]] = None,
    dry_run: bool = True,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if dry_run:
        return op_result(
            action=action,
            summary="Dry run only. No mutation executed.",
            details={"method": method, "path": path, "params": params or {}, "body": body or {}},
            warnings=["Set dry_run=false to execute this mutation."],
        )
    payload = _call_connect_api(oauth_session, method, path, body=body, params=params)
    return op_result(
        action=action,
        summary="Mutation executed successfully.",
        details={"method": method, "path": path, "response": payload},
    )


def safe_read(
    oauth_session: OAuthSession,
    action: str,
    path: str,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = _call_connect_api(oauth_session, "GET", path, params=params)
    return op_result(
        action=action,
        summary="Read executed successfully.",
        details={"path": path, "response": payload},
    )


def build_ssot_path(resource: str) -> str:
    clean = resource.strip("/")
    return f"/services/data/{API_VERSION}/ssot/{clean}"
