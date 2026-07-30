from __future__ import annotations

import html
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from .contracts import op_result


def _parse_xml_files(root: Path, glob_pattern: str) -> List[Dict]:
    out: List[Dict] = []
    for path in root.glob(glob_pattern):
        try:
            tree = ET.parse(path)
            node = tree.getroot()
            out.append(
                {
                    "file": str(path),
                    "root_tag": node.tag,
                    "child_tags": [child.tag for child in list(node)[:25]],
                }
            )
        except Exception as exc:
            out.append({"file": str(path), "error": str(exc)})
    return out


def generate_blueprint_artifacts(metadata_root: Path, output_root: Path, brand_name: str) -> Dict:
    streams = _parse_xml_files(metadata_root, "**/*DataStream*.xml")
    identity = _parse_xml_files(metadata_root, "**/*Identity*Resolution*.xml")
    graphs = _parse_xml_files(metadata_root, "**/*DataGraph*.xml")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "brand_name": brand_name,
        "metadata_root": str(metadata_root),
        "counts": {
            "streams": len(streams),
            "identity_resolutions": len(identity),
            "data_graphs": len(graphs),
        },
        "streams": streams,
        "identity_resolutions": identity,
        "data_graphs": graphs,
    }

    output_root.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_root / f"blueprint_{ts}.json"
    html_path = output_root / f"blueprint_{ts}.html"

    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    html_body = _render_html(payload)
    html_path.write_text(html_body, encoding="utf-8")

    return op_result(
        action="generate_blueprint",
        summary="Blueprint artifacts generated.",
        details={
            "json_path": str(json_path),
            "html_path": str(html_path),
            "counts": payload["counts"],
        },
    )


def _render_html(payload: Dict) -> str:
    def render_list(title: str, items: List[Dict]) -> str:
        cards: List[str] = []
        for item in items:
            cards.append(
                "<div class='card'><pre>{}</pre></div>".format(
                    html.escape(json.dumps(item, indent=2))
                )
            )
        return f"<section><h2>{html.escape(title)}</h2>{''.join(cards) or '<p>None found</p>'}</section>"

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>{html.escape(payload['brand_name'])} Data360 Blueprint</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; background: #0f172a; color: #e2e8f0; }}
    h1, h2 {{ color: #93c5fd; }}
    .meta {{ padding: 12px; background: #1e293b; border-radius: 8px; margin-bottom: 16px; }}
    .card {{ background: #1e293b; border-radius: 8px; padding: 12px; margin-bottom: 12px; }}
    pre {{ white-space: pre-wrap; word-break: break-word; }}
  </style>
</head>
<body>
  <h1>{html.escape(payload['brand_name'])} Data360 Blueprint</h1>
  <div class="meta">
    <p><strong>Generated:</strong> {html.escape(payload['generated_at'])}</p>
    <p><strong>Metadata root:</strong> {html.escape(payload['metadata_root'])}</p>
    <p><strong>Counts:</strong> {html.escape(json.dumps(payload['counts']))}</p>
  </div>
  {render_list("Data Streams", payload["streams"])}
  {render_list("Identity Resolutions", payload["identity_resolutions"])}
  {render_list("Data Graphs", payload["data_graphs"])}
</body>
</html>
"""
