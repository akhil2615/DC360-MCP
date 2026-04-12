# Salesforce Data Cloud MCP Server

An MCP (Model Context Protocol) server that gives Cursor AI live access to your
Salesforce Data Cloud org, enabling AI-assisted authoring of formulas, streaming
transforms, calculated insight SQL, segment logic, and ad-hoc troubleshooting queries.

Built on top of the [datacloud-mcp-query](https://github.com/forcedotcom/datacloud-mcp-query)
example by Salesforce, extended with metadata APIs, code generation tools, and a
comprehensive Cursor skill with battle-tested syntax rules.

## What it does

| Category | Tool | Description |
|----------|------|-------------|
| **Schema Discovery** | `list_data_lake_objects` | Browse all raw DLOs in your org |
| | `describe_data_lake_object` | Inspect DLO fields before writing formulas |
| | `list_data_model_objects` | Browse all harmonised DMOs |
| | `describe_data_model_object` | Inspect DMO fields before writing SQL / segments |
| | `list_calculated_insights` | See all existing calculated insights |
| | `describe_calculated_insight` | Understand an insight's dimensions & measures |
| **Code Generation** | `generate_formula` | Write Data Stream formula field expressions |
| | `generate_streaming_transform` | Write streaming transform SQL |
| | `generate_calculated_insight_sql` | Write valid Calculated Insight SQL |
| | `generate_segment_logic` | Build segment filter expressions |
| **Query & Troubleshoot** | `query` | Execute SQL in the Data Cloud query engine |
| | `list_tables` | Quick table inventory via pg_catalog |
| | `describe_table` | Column list via pg_catalog |
| | `troubleshoot_data` | Diagnose data quality issues with targeted queries |
| **Documentation** | `export_dlo_fields` | Export DLO fields for documentation |
| | `export_dmo_fields` | Export DMO fields with primary key info |
| | `export_dlo_to_dmo_mapping` | Export DLO-to-DMO field mapping template |
| | `export_dmo_relationships` | Export DMO-to-DMO relationship map |
| **Utility** | `debug_auth` | Show resolved SF and DC instance URLs |
| | `datacloud_help` | Answer any conceptual Data Cloud question |

## Cursor Skill (included)

The `.cursor/skills/salesforce-datacloud/` directory contains a comprehensive skill
that teaches Cursor the correct syntax for every Data Cloud feature:

- **Formula fields** — `sourceField['Label']` syntax, AND/OR as infix operators,
  double-quoted strings, supported functions (IF, LEFT, PROPER, NOW, etc.)
- **Streaming transforms** — `DLOName__dll.Field__c` dot notation, explicit AS aliases,
  single-quoted strings, no comments, SUBSTRING instead of LEFT, ISNULL/ISNOTNULL
- **Calculated Insights** — `__c` suffix aliases, GROUP BY aliases, CDPHour(),
  NTILE/RANK/DENSE_RANK, inline views, standard join paths
- **Query Editor** — table aliases, ROW_NUMBER(), date arithmetic, JOIN ON with parens
- **Segments** — all 6 segment types, operators by data type, containers, aggregation,
  container paths, nested operators, best practices
- **Documentation exports** — DLO/DMO field lists, DLO→DMO mapping, DMO relationships

All syntax rules were validated against a real Data Cloud org and corrected iteratively.

## Prerequisites

- Python 3.10+
- A Salesforce org with Data Cloud provisioned
- A Connected App with the correct OAuth scopes

## Quick Start

### 1. Clone the repo

```bash
git clone https://github.com/<your-org>/datacloud-mcp.git
cd datacloud-mcp
```

### 2. Create a virtual environment and install dependencies

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Create a Connected App in Salesforce

Follow the detailed steps in [CONNECTED_APP_SETUP.md](CONNECTED_APP_SETUP.md).

Required OAuth scopes:
- `api`
- `cdp_query_api`
- `cdp_profile_api`
- `cdp_ingest_api`

### 4. Add the MCP server to Cursor

Open **Cursor Settings → MCP → Edit Config** and add:

```jsonc
{
  "mcpServers": {
    "datacloud": {
      "command": "/path/to/.venv/bin/python",
      "args": ["/path/to/datacloud-mcp/server.py"],
      "env": {
        "SF_CLIENT_ID": "<your-consumer-key>",
        "SF_CLIENT_SECRET": "<your-consumer-secret>",
        "SF_LOGIN_URL": "login.salesforce.com",
        "SF_CALLBACK_URL": "http://localhost:55556/Callback"
      },
      "disabled": false,
      "autoApprove": [
        "list_data_lake_objects",
        "list_data_model_objects",
        "list_calculated_insights",
        "list_tables",
        "describe_data_lake_object",
        "describe_data_model_object",
        "describe_calculated_insight",
        "describe_table",
        "debug_auth"
      ]
    }
  }
}
```

> **Windows paths**: use `C:\\path\\to\\.venv\\Scripts\\python.exe`
> **Sandbox orgs**: set `"SF_LOGIN_URL": "test.salesforce.com"`

### 5. Install the Cursor Skill

Copy the skill directory to your personal skills folder:

```bash
# macOS / Linux
cp -r .cursor/skills/salesforce-datacloud ~/.cursor/skills/

# Windows (PowerShell)
Copy-Item -Recurse .cursor\skills\salesforce-datacloud $env:USERPROFILE\.cursor\skills\
```

The skill will be automatically discovered by Cursor on the next chat.

### 6. Reload MCP in Cursor

Go to **Cursor Settings → MCP**, find `datacloud`, and click **Refresh**.
On first use, a browser window will open for Salesforce OAuth login.

## Authentication Flow

```
1. Browser OAuth2 PKCE → SF access_token + sf_instance_url
2. POST {sf_instance_url}/services/a360/token → DC access_token + c360a_url
```

The SF token is used for the Query API (`/services/data/v63.0/ssot/query-sql`).
The DC token is used for the Metadata API (`{c360a_url}/api/v1/metadata/`).
Both tokens auto-refresh after ~110 minutes.

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SF_CLIENT_ID` | Yes | — | Connected App Consumer Key |
| `SF_CLIENT_SECRET` | Yes | — | Connected App Consumer Secret |
| `SF_LOGIN_URL` | No | `login.salesforce.com` | Use `test.salesforce.com` for sandbox |
| `SF_CALLBACK_URL` | No | `http://localhost:55556/Callback` | OAuth redirect URI |
| `DEFAULT_LIST_TABLE_FILTER` | No | `%` | SQL LIKE filter for `list_tables` |

## Architecture

```
server.py              — MCP tools (FastMCP) — 20 tools
oauth.py               — Two-step OAuth: SF PKCE + DC a360 token exchange
connect_api_dc_sql.py  — Data Cloud Query API with long-polling & pagination
dc_metadata_api.py     — /api/v1/metadata wrapper (REST primary, SQL fallback)

.cursor/skills/salesforce-datacloud/
├── SKILL.md                  — Cursor skill: workflows, syntax rules, best practices
└── dc-syntax-reference.md    — Full reference: operators, functions, templates, examples
```

## Usage Examples

### Generate a formula field

> "Write a formula for Lead_Home__dll that flags junk emails as Yes/No"

### Write a streaming transform

> "Create a streaming transform for Lead_Home__dll that cleanses email, phone,
> first/last name and classifies IR readiness"

### Write a Calculated Insight

> "Write a CI that calculates lifetime spend per unified individual,
> ranked by total amount"

### Build a segment

> "Create a segment for customers in the US who purchased at least twice in the
> last 90 days with total spend > $500"

### Troubleshoot data

> "Emails are null in UnifiedIndividual after today's CRM data stream run.
> Write queries to investigate."

### Document your data model

> "Export all fields from Lead_Home__dll to a CSV with DMO mappings"

## Syntax Rules Summary

The skill contains battle-tested syntax rules for each Data Cloud feature:

| Feature | Key syntax difference |
|---------|----------------------|
| Formula fields | `sourceField['Label']`, AND/OR infix, double-quoted strings |
| Streaming transforms | `DLO__dll.Field__c AS Field__c`, single-quoted strings, no comments, no LEFT() |
| Calculated Insights | `__c` suffix aliases, GROUP BY aliases, no double-quoting |
| Query Editor | Table aliases, ROW_NUMBER(), comments OK, LIMIT 10000 |
| Segments | Structured Segment Builder steps with containers and aggregation |

## License

Apache 2.0
