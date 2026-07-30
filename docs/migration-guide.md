# Migration Guide

This guide maps legacy usage to the consolidated platform.

## Existing tools (unchanged)

All existing schema/query/generation tools remain available with the same names.

## New operational tools

- DLO lifecycle: `create_dlo`, `update_dlo`, `delete_dlo`
- Segment lifecycle: `create_segment`, `update_segment`, `delete_segment`
- Activation lifecycle: `update_activation`, `delete_activation`
- Mapping lifecycle: `create_dlo_dmo_mapping`, `update_dlo_dmo_mapping`, `delete_dlo_dmo_mapping`
- Transform lifecycle: `create_data_transform`, `update_data_transform`, `delete_data_transform`, `get_data_transform_run_history`
- Data graph lifecycle: `list_data_graphs`, `create_data_graph`, `delete_data_graph`

## New workflow tools

- Drift + pipeline: `run_org_diff`, `pipeline_retrieve`, `pipeline_promote`, `pipeline_deploy_check`
- Architecture docs: `generate_blueprint`

## Default mutation behavior

Most new write/delete operations require explicit opt-in by setting `dry_run=false`.
