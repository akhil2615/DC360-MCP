from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, List

from .contracts import op_result


def _run_cmd(command: List[str], cwd: Path) -> Dict:
    proc = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True)
    return {
        "command": " ".join(command),
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def run_git_diff_mode(mode: str, left: str, right: str, repo_root: Path) -> Dict:
    if mode == "branch-vs-branch":
        return _run_cmd(["git", "diff", f"{left}...{right}"], repo_root)
    if mode == "org-vs-branch":
        # Placeholder pattern: compare working tree with branch head.
        return _run_cmd(["git", "diff", left], repo_root)
    if mode == "org-vs-org":
        # For org-vs-org we rely on materialized metadata folders.
        left_path = Path(left)
        right_path = Path(right)
        if not left_path.exists() or not right_path.exists():
            raise ValueError("For org-vs-org mode, left/right must be existing local folder paths.")
        return _run_cmd(
            ["git", "diff", "--no-index", str(left_path), str(right_path)],
            repo_root,
        )
    raise ValueError(f"Unsupported mode: {mode}")


def retrieve_metadata(repo_root: Path, org_alias: str, manifest_path: str, dry_run: bool) -> Dict:
    cmd = ["sf", "project", "retrieve", "start", "-o", org_alias, "-x", manifest_path]
    if dry_run:
        return op_result(
            action="pipeline_retrieve",
            summary="Dry run only. Retrieve command not executed.",
            details={"command": " ".join(cmd)},
            warnings=["Set dry_run=false to execute retrieve."],
        )
    result = _run_cmd(cmd, repo_root)
    return op_result("pipeline_retrieve", "Retrieve command completed.", details=result, ok=result["exit_code"] == 0)


def deploy_check(repo_root: Path, org_alias: str, manifest_path: str, dry_run: bool) -> Dict:
    cmd = ["sf", "project", "deploy", "start", "-o", org_alias, "-x", manifest_path, "--check-only"]
    if dry_run:
        return op_result(
            action="pipeline_deploy_check",
            summary="Dry run only. Deploy check command not executed.",
            details={"command": " ".join(cmd)},
            warnings=["Set dry_run=false to execute check-only deploy."],
        )
    result = _run_cmd(cmd, repo_root)
    return op_result("pipeline_deploy_check", "Deploy check completed.", details=result, ok=result["exit_code"] == 0)
