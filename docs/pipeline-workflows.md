# Pipeline Workflows

The unified repo includes MCP tools for deployment-style workflows:

- `run_org_diff`
- `pipeline_retrieve`
- `pipeline_promote`
- `pipeline_deploy_check`

## Drift modes

- `branch-vs-branch`: compares git branches directly.
- `org-vs-branch`: compares working state against a branch baseline.
- `org-vs-org`: compares two local metadata folders using `git diff --no-index`.

## Promotion sequence

1. Retrieve from source org:
   - `pipeline_retrieve(org_alias, manifest_path, dry_run=true|false)`
2. Validate promotion command:
   - `pipeline_promote(source_branch, target_branch, dry_run=true)`
3. Run check-only deploy:
   - `pipeline_deploy_check(org_alias, manifest_path, dry_run=false)`

## Safety defaults

- Mutation-equivalent operations default to `dry_run=true`.
- `pipeline_promote` only returns a reviewed command plan and does not auto-merge.
