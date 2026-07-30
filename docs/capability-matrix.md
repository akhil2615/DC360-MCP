# Data360 Consolidation Capability Matrix

This matrix maps the unified platform scope across:
- `DC360-MCP` (current repo)
- `data360-mcp` (FLASH)
- `d360-skill-org-diff`
- `d360-skill-deploy`
- `d360-skill-blueprint`

## Canonical Tool Contract Rules

- Keep existing tool names backward compatible where possible.
- Add aliases only when a rename is necessary.
- Standardize mutation tools to support `dry_run` whenever practical.
- Normalize operational output shape:
  - `ok` (bool)
  - `action` (string)
  - `summary` (string)
  - `details` (dict/list)
  - `warnings` (list of strings, optional)

## Capability Mapping

| Domain | Existing in this repo | FLASH parity needed | Skill repo parity needed | Unified canonical domain |
|---|---|---|---|---|
| Query | `query`, `list_tables`, `describe_table` | Keep | N/A | `query_tools` |
| Metadata discovery | DLO/DMO/CI list + describe | Keep | N/A | `metadata_tools` |
| Prompt generators | Formula/streaming/CI/segment helpers | Keep | N/A | `authoring_tools` |
| Org inventory | spaces/sources/connectors/streams/segments/transforms/activations | Keep + extend | N/A | `inventory_tools` |
| DLO lifecycle | No create/update/delete | Add | N/A | `dlo_tools` |
| DMO lifecycle | No create/update/delete fields | Add | N/A | `dmo_tools` |
| DLO-DMO mappings | Export template only | Add create/update/delete | N/A | `mapping_tools` |
| Segment lifecycle | List + generation only | Add create/update/delete | N/A | `segment_tools` |
| Activation lifecycle | List only | Add read/update/delete | N/A | `activation_tools` |
| Data transforms lifecycle | List only | Add create/update/delete/history | N/A | `transform_tools` |
| Data graph lifecycle | Not present | Add list/create/delete | Blueprint uses graph metadata | `graph_tools` |
| Data actions/targets | Not present | Add list/create/delete | N/A | `data_action_tools` |
| Data space operations | List only | Add get/update/member introspection | N/A | `dataspace_tools` |
| Drift detection | Not present | N/A | Add org-vs-branch/org-vs-org/branch-vs-branch | `pipeline_diff_tools` |
| Promotion deploy workflow | Not present | N/A | Add retrieve/promote/deploy helpers | `pipeline_deploy_tools` |
| Blueprint documentation | Not present | N/A | Add parse/render HTML blueprint | `blueprint_tools` |

## Backward-Compatibility Aliases

- Preserve current names unchanged for existing tools.
- Introduce additive names for new operations, for example:
  - `create_dlo`, `update_dlo`, `delete_dlo`
  - `create_custom_dmo`, `create_custom_dmo_fields`, `delete_custom_dmo_fields`
  - `create_dlo_dmo_mapping`, `update_dlo_dmo_mapping`, `delete_dlo_dmo_mapping`
  - `create_segment`, `update_segment`, `delete_segment`
  - `get_activation_details`, `update_activation`, `delete_activation`
  - `create_data_transform`, `update_data_transform`, `delete_data_transform`, `get_data_transform_run_history`
  - `list_data_graphs`, `create_data_graph`, `delete_data_graph`
  - `run_org_diff`, `pipeline_retrieve`, `pipeline_promote`, `pipeline_deploy_check`
  - `generate_blueprint`

## Dependency and Risk Notes

- `pipeline_*` tools depend on local `git` and optional `sf` CLI.
- Some Data Cloud mutation APIs vary by org/api version; tools should expose fallback + clear warnings.
- Drift false positives remain possible where Salesforce metadata retrieval omits/deforms deletions.
