# Salesforce Data Cloud MCP Server

An MCP (Model Context Protocol) server that gives Cursor AI live access to your
Salesforce Data Cloud org — enabling AI-assisted authoring of formulas, streaming
transforms, calculated insight SQL, segment logic, and ad-hoc troubleshooting queries.

## What it does

| Tool | What Cursor can do with it |
|------|---------------------------|
| `list_data_lake_objects` | Browse all raw DLOs in your org |
| `describe_data_lake_object` | Inspect fields before writing formulas |
| `list_data_model_objects` | Browse all harmonised DMOs |
| `describe_data_model_object` | Inspect DMO fields before writing SQL / segments |
| `list_calculated_insights` | See all existing calculated insights |
| `describe_calculated_insight` | Understand an insight's dimensions & measures |
| `generate_formula` | Write Data Stream formula field expressions |
| `generate_streaming_transform` | Write streaming transform mapping SQL |
| `generate_calculated_insight_sql` | Write valid Calculated Insight SQL |
| `generate_segment_logic` | Build segment filter expressions |
| `query` | Execute SQL in the Data Cloud query engine |
| `list_tables` | Quick table inventory via pg_catalog |
| `describe_table` | Column list via pg_catalog |
| `troubleshoot_data` | Diagnose data quality issues with targeted queries |
| `datacloud_help` | Answer any conceptual Data Cloud question |

## Prerequisites

- Python 3.10+
- A Salesforce org with Data Cloud provisioned
- A Connected App with the correct OAuth scopes

## Setup

### 1. Clone / copy this project

```bash
git clone <your-repo-url> datacloud-mcp
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

### 3. Create a Connected App

Follow the detailed steps in [CONNECTED_APP_SETUP.md](CONNECTED_APP_SETUP.md).

### 4. Add to Cursor

Open **Cursor Settings → MCP → Edit config** and add:

```jsonc
{
  "mcpServers": {
    "datacloud": {
      "command": "C:/path/to/.venv/Scripts/python.exe",
      "args": ["C:/path/to/datacloud-mcp/server.py"],
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
        "describe_table"
      ]
    }
  }
}
```

> **Tip — Sandbox orgs**: set `"SF_LOGIN_URL": "test.salesforce.com"`.

### 5. Reload MCP in Cursor

Go to **Cursor Settings → MCP**, find `datacloud`, and click **Refresh**.  
On first use, a browser window will open for Salesforce OAuth login.

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SF_CLIENT_ID` | Yes | — | Connected App Consumer Key |
| `SF_CLIENT_SECRET` | Yes | — | Connected App Consumer Secret |
| `SF_LOGIN_URL` | No | `login.salesforce.com` | Use `test.salesforce.com` for sandbox |
| `SF_CALLBACK_URL` | No | `http://localhost:55556/Callback` | OAuth redirect URI |
| `DEFAULT_LIST_TABLE_FILTER` | No | `%` | SQL LIKE filter for `list_tables` |

## Usage examples

### Generate a formula field

> "Using the `WebActivity__dll` data lake object, write a formula that extracts
> the domain from the `PageURL__c` field."

Cursor will call `describe_data_lake_object("WebActivity__dll")` automatically,
then generate a syntactically valid formula using the available fields.

### Write a Calculated Insight

> "Write a Calculated Insight SQL that calculates total purchase value per unified
> individual over the last 90 days, joining `UnifiedIndividual__dlm` and
> `SalesOrder__dlm`."

### Build a segment

> "Create segment logic for customers in Germany who purchased more than twice
> in the last 6 months and are opted in to email."

### Troubleshoot data

> "Emails are null in `UnifiedIndividual__dlm` after today's CRM data stream run.
> Write SQL to investigate."

## Architecture

```
server.py              — MCP tools (FastMCP)
oauth.py               — OAuth2 PKCE browser flow
connect_api_dc_sql.py  — Data Cloud Query API with long-polling & pagination
dc_metadata_api.py     — /api/v1/metadata wrapper for DLO / DMO / CI schemas
```

## License

Apache 2.0
