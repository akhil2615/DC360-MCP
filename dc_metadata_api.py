"""
Data Cloud Metadata

Primary path  : GET {c360a_url}/api/v1/metadata/  (Data Cloud Direct API)
                Uses the DC token from the two-step auth flow.
Fallback path : pg_catalog SQL via the SSOT Query API
                Used automatically if the REST call fails (e.g. perm issue).

Two-step auth recap
───────────────────
1. Standard Salesforce OAuth  → SF token  +  sf_instance_url
2. POST {sf_instance_url}/services/a360/token
     grant_type          = urn:salesforce:grant-type:external:cdp
     subject_token       = <SF token>
     subject_token_type  = urn:ietf:params:oauth:token-type:access_token
   → DC token  +  c360a_url  (scheme://host only, path stripped)

Metadata endpoint  : GET {c360a_url}/api/v1/metadata/
  ?entityType       = DataLakeObject | DataModelObject | CalculatedInsight
  ?entityCategory   = Profile | Engagement | Related
  ?entityName       = <exact api name>

Reference: https://developer.salesforce.com/docs/data/data-cloud-query-guide/
           references/data-cloud-query-api-reference/c360a-api-metadata-api.html
"""
import json
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests

from connect_api_dc_sql import run_query
from oauth import OAuthSession


def _parse_display_name(raw: Any) -> str:
    """
    The REST metadata API returns displayName as a JSON-encoded string like
    '{"displayName":"Email","entityCategory":"Profile",...}'.
    Extract just the displayName value; fall back to the raw string.
    """
    if not raw or not isinstance(raw, str):
        return str(raw) if raw else ""
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed.get("displayName", raw)
    except (json.JSONDecodeError, TypeError):
        pass
    return raw

logger = logging.getLogger(__name__)

ENTITY_TYPE_DLO = "DataLakeObject"
ENTITY_TYPE_DMO = "DataModelObject"
ENTITY_TYPE_CI  = "CalculatedInsight"

# pg_catalog suffix patterns used in the SQL fallback
_SUFFIX_MAP = {
    ENTITY_TYPE_DLO: "%__dll",
    ENTITY_TYPE_DMO: "%__dlm",
    ENTITY_TYPE_CI:  "%__insight",
}

# ---------------------------------------------------------------------------
# Primary: REST metadata API
# ---------------------------------------------------------------------------

def _rest_get_metadata(
    oauth_session: OAuthSession,
    entity_type: Optional[str] = None,
    entity_category: Optional[str] = None,
    entity_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Call GET {c360a_url}/api/v1/metadata/ and return the entity list.
    Raises on any HTTP error so the caller can fall back to SQL.
    """
    base_url = oauth_session.get_dc_instance_url()
    token    = oauth_session.get_dc_token()

    # Safety: strip any residual path so we always hit scheme://host/api/v1/metadata/
    parsed = urlparse(base_url)
    clean_base = f"{parsed.scheme}://{parsed.netloc}"
    url = f"{clean_base}/api/v1/metadata/"

    params: dict = {}
    if entity_type:
        params["entityType"] = entity_type
    if entity_category:
        params["entityCategory"] = entity_category
    if entity_name:
        params["entityName"] = entity_name

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    logger.info(f"REST metadata API → {url}  params={params}")
    response = requests.get(url, params=params, headers=headers, timeout=60)
    logger.info(f"REST metadata response: {response.status_code}")

    response.raise_for_status()          # caller catches and falls back

    payload = response.json()
    if isinstance(payload, dict):
        return payload.get("metadata", [])
    return payload


# ---------------------------------------------------------------------------
# Fallback: pg_catalog SQL via the working SSOT Query API
# ---------------------------------------------------------------------------

_LIST_SQL = """
SELECT
    c.relname                           AS name,
    COALESCE(d.description, c.relname)  AS display_name
FROM pg_catalog.pg_class c
LEFT JOIN pg_catalog.pg_description d
    ON d.objoid = c.oid AND d.objsubid = 0
WHERE c.relkind IN ('r','v','m','f')
  AND c.relname LIKE '{pattern}'
ORDER BY c.relname
"""

_FIELDS_SQL = """
SELECT
    a.attname                             AS field_name,
    t.typname                             AS field_type,
    COALESCE(dsc.description, a.attname)  AS display_name
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_attribute a   ON a.attrelid = c.oid
JOIN pg_catalog.pg_type t        ON t.oid = a.atttypid
LEFT JOIN pg_catalog.pg_description dsc
    ON dsc.objoid = c.oid AND dsc.objsubid = a.attnum
WHERE a.attnum > 0
  AND NOT a.attisdropped
  AND c.relname = '{table}'
ORDER BY a.attnum
"""


def _sql_list_objects(
    oauth_session: OAuthSession, entity_type: str
) -> List[Dict[str, Any]]:
    pattern = _SUFFIX_MAP.get(entity_type, "%")
    result  = run_query(oauth_session, _LIST_SQL.format(pattern=pattern))
    return [
        {"name": row[0], "displayName": row[1], "category": entity_type}
        for row in result.get("data", [])
    ]


def _sql_get_fields(
    oauth_session: OAuthSession, entity_name: str
) -> List[Dict[str, Any]]:
    result = run_query(oauth_session, _FIELDS_SQL.format(table=entity_name))
    return [
        {"name": row[0], "type": row[1], "displayName": row[2]}
        for row in result.get("data", [])
    ]


# ---------------------------------------------------------------------------
# Public helpers — REST first, SQL fallback
# ---------------------------------------------------------------------------

def list_objects(
    oauth_session: OAuthSession, entity_type: str
) -> List[Dict[str, Any]]:
    """Return a compact list of objects for the given entity type."""
    try:
        entities = _rest_get_metadata(oauth_session, entity_type=entity_type)
        return [
            {
                "name":        e.get("name"),
                "displayName": _parse_display_name(e.get("displayName", e.get("name"))),
                "category":    e.get("category", entity_type),
            }
            for e in entities
        ]
    except Exception as e:
        logger.warning(f"REST metadata failed ({e}), falling back to SQL")
        return _sql_list_objects(oauth_session, entity_type)


def describe_object(
    oauth_session: OAuthSession,
    entity_name: str,
    entity_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Return full schema for a single named entity."""
    try:
        entities = _rest_get_metadata(
            oauth_session, entity_type=entity_type, entity_name=entity_name
        )
        if entities:
            return entities[0]
        raise ValueError(f"No entity found: '{entity_name}'")
    except ValueError:
        raise
    except Exception as e:
        logger.warning(f"REST metadata failed ({e}), falling back to SQL")
        fields = _sql_get_fields(oauth_session, entity_name)
        if not fields:
            raise ValueError(
                f"No object found named '{entity_name}'. "
                "Verify the name with list_data_lake_objects / list_data_model_objects."
            )
        return {"name": entity_name, "category": entity_type or "unknown", "fields": fields}


def get_fields_for_object(
    oauth_session: OAuthSession,
    entity_name: str,
    entity_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return the field list for a given entity."""
    try:
        entity = describe_object(oauth_session, entity_name, entity_type)
        return entity.get("fields", [])
    except Exception:
        return _sql_get_fields(oauth_session, entity_name)


def get_raw_metadata(
    oauth_session: OAuthSession,
    entity_type: Optional[str] = None,
    entity_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return the unprocessed metadata response including primaryKeys, relationships, category."""
    try:
        return _rest_get_metadata(oauth_session, entity_type=entity_type, entity_name=entity_name)
    except Exception as e:
        logger.warning(f"REST metadata failed ({e}), raw metadata not available via SQL fallback")
        return []
