import json
import logging
from typing import Dict, List, Union

import requests

from oauth import OAuthSession

logger = logging.getLogger(__name__)


def _handle_error_response(response: requests.Response):
    if response.status_code >= 300:
        message = response.text
        try:
            payload = json.loads(response.text)
            if isinstance(payload, list) and len(payload) > 0:
                structured_message = payload[0]
                try:
                    errors_details_json = structured_message.get("message", "")
                    details = json.loads(errors_details_json) if errors_details_json else None
                    if details:
                        message = errors_details_json
                except Exception:
                    pass
        except Exception:
            pass
        raise Exception(response.status_code, response.reason, message)


def run_query(
    oauth_session: OAuthSession,
    sql: str,
    dataspace: str = "default",
    workload_name: str | None = "datacloud-mcp",
    pagination_batch_size: int = 100_000,
) -> Dict[str, Union[List, str]]:
    """Execute a SQL query via the Data Cloud Query Connect API with pagination."""
    base_url = oauth_session.get_instance_url()
    token = oauth_session.get_token()

    headers = {"Authorization": f"Bearer {token}"}
    url_base = base_url + "/services/data/v63.0/ssot/query-sql"
    common_params: dict = {"dataspace": dataspace}
    if workload_name:
        common_params["workloadName"] = workload_name

    submit_body = {"sql": sql}
    logger.info(f"Submitting SQL query to {url_base}")

    submit_response = requests.post(
        url_base, json=submit_body, params=common_params, headers=headers, timeout=120
    )
    logger.info(
        f"Query submission: status={submit_response.status_code}, "
        f"elapsed={submit_response.elapsed.total_seconds():.2f}s"
    )
    _handle_error_response(submit_response)

    submit_payload = submit_response.json()
    status_obj = submit_payload.get("status", {})
    query_id = status_obj.get("queryId") or submit_payload.get("queryId")
    if not query_id:
        raise Exception(500, "MissingQueryId", "Query ID not returned by the API.")

    rows: list = submit_payload.get("data", []) or []
    metadata = submit_payload.get("metadata", [])
    completion = status_obj.get("completionStatus")
    total_row_count = int(status_obj.get("rowCount", 0))

    poll_count = 0
    while completion not in ["Finished", "ResultsProduced"]:
        poll_count += 1
        poll_url = f"{url_base}/{query_id}"
        poll_params = {**common_params, "waitTimeMs": 10000}
        poll_response = requests.get(poll_url, params=poll_params, headers=headers, timeout=120)
        _handle_error_response(poll_response)
        poll_payload = poll_response.json()
        completion = poll_payload.get("completionStatus")
        total_row_count = int(poll_payload.get("rowCount", 0))

    while len(rows) < total_row_count:
        rows_params = {
            **common_params,
            "rowLimit": pagination_batch_size,
            "offset": len(rows),
            "omitSchema": "true",
        }
        rows_url = f"{url_base}/{query_id}/rows"
        rows_response = requests.get(rows_url, params=rows_params, headers=headers, timeout=120)
        _handle_error_response(rows_response)

        chunk = rows_response.json()
        chunk_rows = chunk.get("data", []) or []
        returned_rows = int(chunk.get("returnedRows", len(chunk_rows)))
        if returned_rows == 0:
            raise Exception(500, "MissingRows", "Expected rows but received 0.")
        rows.extend(chunk_rows)

    logger.info(f"Query completed: {len(rows)} total rows retrieved")
    return {"data": rows, "metadata": metadata}
