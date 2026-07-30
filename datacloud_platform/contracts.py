from __future__ import annotations

from typing import Any, Dict, List


def op_result(
    action: str,
    summary: str,
    details: Dict[str, Any] | List[Any] | None = None,
    ok: bool = True,
    warnings: List[str] | None = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "ok": ok,
        "action": action,
        "summary": summary,
        "details": details or {},
    }
    if warnings:
        payload["warnings"] = warnings
    return payload
