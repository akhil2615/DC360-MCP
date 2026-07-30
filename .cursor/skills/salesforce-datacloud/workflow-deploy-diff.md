# Deployment and Drift Workflow

Use this workflow when a user asks to compare environments or promote Data Cloud metadata.

## Steps

1. Run `run_org_diff` in the correct mode:
   - `branch-vs-branch`
   - `org-vs-branch`
   - `org-vs-org`
2. If changes are expected, run `pipeline_retrieve` from source org.
3. Prepare merge with `pipeline_promote` (dry run).
4. Validate target org with `pipeline_deploy_check`.

## Safety

- Keep destructive operations manual and reviewable.
- Always run `pipeline_deploy_check` before actual deployment.
