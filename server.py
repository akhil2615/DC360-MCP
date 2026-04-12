"""
Salesforce Data Cloud MCP Server
Provides Cursor with live access to your Data Cloud org metadata and query engine,
enabling AI-assisted authoring of formulas, streaming transforms, calculated insight SQL,
segment logic, and ad-hoc troubleshooting queries.
"""
import logging
import os

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from oauth import OAuthConfig, OAuthSession
from connect_api_dc_sql import run_query
from dc_metadata_api import (
    ENTITY_TYPE_CI,
    ENTITY_TYPE_DLO,
    ENTITY_TYPE_DMO,
    describe_object,
    get_fields_for_object,
    list_objects,
)

logger = logging.getLogger(__name__)

mcp = FastMCP("Salesforce Data Cloud")

sf_org: OAuthConfig = OAuthConfig.from_env()
oauth_session: OAuthSession = OAuthSession(sf_org)

DEFAULT_LIST_TABLE_FILTER = os.getenv("DEFAULT_LIST_TABLE_FILTER", "%")

# ---------------------------------------------------------------------------
# Schema discovery — Data Lake Objects (DLOs)
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "List all Data Lake Objects (DLOs) in the Data Cloud org. "
        "DLOs represent raw ingested data before harmonisation. "
        "Use this as the first step when authoring Data Stream formulas or "
        "streaming transform mappings."
    )
)
def list_data_lake_objects() -> list[dict]:
    """Returns each DLO with its API name, display name, and category."""
    return list_objects(oauth_session, ENTITY_TYPE_DLO)


@mcp.tool(
    description=(
        "Describe a specific Data Lake Object (DLO): returns every field with "
        "its API name, display name, data type, and associated key qualifier. "
        "Use before writing formula fields or streaming transform expressions "
        "so you reference exact field names."
    )
)
def describe_data_lake_object(
    dlo_name: str = Field(
        description=(
            "The API name of the Data Lake Object, e.g. 'MySource_Home_Page_Views__dll'. "
            "Obtain this from list_data_lake_objects."
        )
    ),
) -> dict:
    return describe_object(oauth_session, dlo_name, ENTITY_TYPE_DLO)


# ---------------------------------------------------------------------------
# Schema discovery — Data Model Objects (DMOs)
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "List all Data Model Objects (DMOs) in the Data Cloud org. "
        "DMOs are the harmonised, canonical data model (e.g. UnifiedIndividual__dlm). "
        "Use this when writing segment logic or calculated insight SQL."
    )
)
def list_data_model_objects() -> list[dict]:
    return list_objects(oauth_session, ENTITY_TYPE_DMO)


@mcp.tool(
    description=(
        "Describe a specific Data Model Object (DMO): returns all fields with "
        "API names, display names, data types, and key qualifiers. "
        "Essential before writing calculated insight SQL or segment filter expressions."
    )
)
def describe_data_model_object(
    dmo_name: str = Field(
        description=(
            "The API name of the Data Model Object, e.g. 'UnifiedIndividual__dlm'. "
            "Obtain this from list_data_model_objects."
        )
    ),
) -> dict:
    return describe_object(oauth_session, dmo_name, ENTITY_TYPE_DMO)


# ---------------------------------------------------------------------------
# Schema discovery — Calculated Insights (CIs)
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "List all Calculated Insights defined in the Data Cloud org. "
        "Returns each insight's API name and display name."
    )
)
def list_calculated_insights() -> list[dict]:
    return list_objects(oauth_session, ENTITY_TYPE_CI)


@mcp.tool(
    description=(
        "Describe a Calculated Insight: returns its dimensions, measures, and SQL definition. "
        "Use this to understand an existing insight before referencing it in segments "
        "or building related insights."
    )
)
def describe_calculated_insight(
    ci_name: str = Field(
        description=(
            "The API name of the Calculated Insight, e.g. 'LifetimeValue__insight'. "
            "Obtain this from list_calculated_insights."
        )
    ),
) -> dict:
    return describe_object(oauth_session, ci_name, ENTITY_TYPE_CI)


# ---------------------------------------------------------------------------
# AI-assisted code generation
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Generate a syntactically valid Data Cloud formula field expression for use "
        "in a Data Stream field mapping. "
        "Always calls describe_data_lake_object first to verify field names and types. "
        "Supports: IF/AND/OR/NOT, LEFT/RIGHT/MID/SUBSTITUTE/TRIM/UPPER/LOWER/LEN, "
        "ABS/NUMBER/TEXT/MD5, PARSEDATE/DATE/DATEDIFF/DAYPRECISION, EXTRACT. "
        "IMPORTANT: sourceField references use the FIELD LABEL (display name), NOT the "
        "API name. Syntax: sourceField['FieldLabel']. Example: sourceField['Email'] "
        "not sourceField['Email__c']."
    )
)
def generate_formula(
    dlo_name: str = Field(
        description="API name of the Data Lake Object whose fields the formula will reference."
    ),
    description: str = Field(
        description=(
            "Plain-language description of what the formula should compute. "
            "Example: 'Convert the string field status to a boolean: true when value is Y, "
            "false when N, null otherwise.'"
        )
    ),
) -> str:
    fields = get_fields_for_object(oauth_session, dlo_name, ENTITY_TYPE_DLO)
    field_summary = "\n".join(
        f"  - Label: {f.get('displayName', f['name'])}  |  API: {f['name']}  |  Type: {f.get('type', 'unknown')}"
        for f in fields
    )
    return (
        f"## Available fields on {dlo_name}\n{field_summary}\n\n"
        f"## Requested formula\n{description}\n\n"
        "## Instructions for the AI assistant\n"
        "Using ONLY the fields listed above, write a Data Cloud formula expression. "
        "Rules:\n"
        "- CRITICAL: Reference source fields by their LABEL (display name), NOT the API name.\n"
        "  Correct:   sourceField['Email']\n"
        "  WRONG:     sourceField['Email__c']\n"
        "- CRITICAL: AND / OR are INFIX OPERATORS, NOT functions.\n"
        "  Correct:   (sourceField['Country'] == \"US\") OR (sourceField['Country'] == \"USA\")\n"
        "  WRONG:     OR(sourceField['Country'] == \"US\", sourceField['Country'] == \"USA\")\n"
        "- String values use DOUBLE QUOTES: sourceField['Email'] == \"test@test.com\"\n"
        "- Use IF(condition, trueValue, falseValue) for branching — nestable\n"
        "- String functions: LEFT(text,n), RIGHT(text,n), MID(text,start,n), "
        "SUBSTITUTE(text,old,new), TRIM(text), UPPER(text), LOWER(text), LEN(text), "
        "PROPER(text), EXTRACT(text,pattern)\n"
        "- Type conversions: NUMBER(text), TEXT(value), MD5(text), ABS(number)\n"
        "- Date functions: PARSEDATE(text,'format'), DATE(year,month,day), "
        "DATEDIFF(unit,start,end), DAYPRECISION(date), NOW(), TODAY()\n"
        "- Never invent field labels — use exactly the Label values listed above\n"
        "- Return null for unhandled cases using the null keyword\n"
    )


@mcp.tool(
    description=(
        "Generate a streaming data transform SQL query for a Data Stream. "
        "Streaming transforms use SQL with DLOName.FieldName dot notation to "
        "reference source fields. They read from a source DLO, run a SQL query, "
        "and output to a target DLO that maps to a DMO. "
        "Inspects both the source DLO and the target DMO to ensure field types align."
    )
)
def generate_streaming_transform(
    source_dlo_name: str = Field(description="API name of the source Data Lake Object."),
    target_dmo_name: str = Field(description="API name of the target Data Model Object."),
    transformation_description: str = Field(
        description=(
            "Plain-language description of the transform logic needed. "
            "Example: 'Normalize phone contacts into separate rows per phone type "
            "using UNION, filtering out nulls.'"
        )
    ),
) -> str:
    source_fields = get_fields_for_object(oauth_session, source_dlo_name, ENTITY_TYPE_DLO)
    target_fields = get_fields_for_object(oauth_session, target_dmo_name, ENTITY_TYPE_DMO)

    src_summary = "\n".join(
        f"  - {source_dlo_name}.{f['name']}  (type: {f.get('type', 'unknown')})"
        for f in source_fields
    )
    tgt_summary = "\n".join(
        f"  - {f['name']}  (type: {f.get('type', 'unknown')})"
        for f in target_fields
    )

    return (
        f"## Source DLO: {source_dlo_name}\n{src_summary}\n\n"
        f"## Target DMO fields: {target_dmo_name}\n{tgt_summary}\n\n"
        f"## Requested transform\n{transformation_description}\n\n"
        "## Instructions for the AI assistant\n"
        "Write a streaming data transform SQL query for Data Cloud. "
        "This is NOT a formula field — different syntax rules apply.\n\n"
        "### CRITICAL SYNTAX RULES\n"
        f"- Reference ALL source fields with DOT NOTATION: {source_dlo_name}.FieldName\n"
        f"  Example: {source_dlo_name}.Email__c, {source_dlo_name}.Phone__c\n"
        f"- The FROM clause uses the FULL DLO name: FROM {source_dlo_name}\n"
        "- EVERY field in SELECT MUST have an explicit AS alias, even pass-throughs:\n"
        f"  CORRECT: {source_dlo_name}.Email__c AS Email__c\n"
        f"  WRONG:   {source_dlo_name}.Email__c\n"
        "- String literals use SINGLE QUOTES: 'Mobile', 'USA'\n"
        "  Double quotes are for identifiers/aliases only\n"
        "- Use ISNOTNULL(field) to check for non-null (not IS NOT NULL)\n"
        "- Use <> for not-equal: field <> ''\n"
        "- NEVER add SQL comments (-- or /* */)\n"
        "- LEFT() is NOT supported — use SUBSTRING(text, start, length) instead\n\n"
        "### Supported functions\n"
        "- String: CONCAT(), LOWER(), UPPER(), TRIM(), LENGTH(), SUBSTRING(), "
        "REPLACE(), REGEXP_REPLACE()\n"
        "- Conditional: CASE WHEN … THEN … ELSE … END, COALESCE(), ISNULL()\n"
        "- Null check: ISNOTNULL(field), ISNULL(field)\n"
        "- Type: CAST(expr AS type), TO_DATE(), TO_TIMESTAMP()\n"
        "- Date: NOW(), TODAY()\n"
        "- Set ops: UNION, UNION ALL between SELECT blocks\n"
        "- Comparison: =, <>, <, >, <=, >=\n"
        "- IN () operator: AVOID using IN() with function results like LOWER()/UPPER(). "
        "Use chained OR comparisons instead:\n"
        "  WRONG:   LOWER(DLO.Field) IN ('a','b','c')\n"
        "  CORRECT: (LOWER(DLO.Field) = 'a' OR LOWER(DLO.Field) = 'b' OR LOWER(DLO.Field) = 'c')\n"
        "- Logical: AND, OR, NOT (infix operators)\n"
        "- WHERE clause: supported for filtering records\n"
        "- JOIN: supported (INNER, LEFT, RIGHT, FULL OUTER) with ON clause\n"
        "- NOT supported: LEFT(), RIGHT(), MID(), FIND()\n\n"
        "### Template\n"
        f"SELECT\n"
        f"    {source_dlo_name}.FieldA AS FieldA,\n"
        f"    CASE WHEN {source_dlo_name}.FieldB = 'value' THEN 'result' ELSE NULL END AS DerivedField\n"
        f"FROM {source_dlo_name}\n"
        f"WHERE ISNOTNULL({source_dlo_name}.FieldA)\n"
    )


@mcp.tool(
    description=(
        "Generate syntactically valid SQL for a Calculated Insight in Data Cloud. "
        "Data Cloud SQL follows PostgreSQL dialect with these constraints: "
        "always double-quote identifiers, use __dlm suffix for DMO tables, "
        "GROUP BY is required for all aggregates, no subqueries in FROM, "
        "window functions are supported. "
        "Inspects the relevant DMO schemas before generating."
    )
)
def generate_calculated_insight_sql(
    dmo_names: list[str] = Field(
        description=(
            "List of DMO API names to include in the insight, "
            "e.g. ['UnifiedIndividual__dlm', 'SalesOrder__dlm']. "
            "Obtain names from list_data_model_objects."
        )
    ),
    insight_description: str = Field(
        description=(
            "Plain-language description of what the insight should calculate. "
            "Example: 'Total lifetime spend per unified individual, "
            "segmented by country, for the last 12 months.'"
        )
    ),
) -> str:
    schema_blocks = []
    for dmo in dmo_names:
        fields = get_fields_for_object(oauth_session, dmo, ENTITY_TYPE_DMO)
        field_list = "\n".join(
            f"    - \"{f['name']}\" ({f.get('type', 'unknown')})" for f in fields
        )
        schema_blocks.append(f"### {dmo}\n{field_list}")

    schema_text = "\n\n".join(schema_blocks)

    return (
        f"## DMO schemas\n{schema_text}\n\n"
        f"## Requested insight\n{insight_description}\n\n"
        "## Instructions for the AI assistant\n"
        "Write a valid Data Cloud Calculated Insight SQL statement. Rules:\n"
        "- Always double-quote ALL identifiers (tables and columns): "
        'e.g. SELECT "Email__c" FROM "UnifiedIndividual__dlm"\n'
        "- DMO table names always end in __dlm\n"
        "- Calculated Insight measures must use aggregate functions: "
        "SUM(), COUNT(), COUNT(DISTINCT), AVG(), MIN(), MAX()\n"
        "- Every non-aggregated column in SELECT must appear in GROUP BY\n"
        "- Use standard JOIN syntax: "
        'JOIN "OtherObject__dlm" ON "t1"."Id__c" = "t2"."IndividualId__c"\n'
        "- Time filtering: use DATE_TRUNC(), CURRENT_DATE, INTERVAL, "
        "or DATEADD() for relative date ranges\n"
        "- No correlated subqueries; use CTEs (WITH … AS (…)) instead\n"
        "- Use only field names listed in the schemas above\n"
        "- Format the SQL with clear indentation for readability\n"
    )


@mcp.tool(
    description=(
        "Generate segment filter logic for a Data Cloud segment. "
        "Scans the full data model to suggest the correct DMO, field API names, "
        "and valid filter operators. Output is in the format used by the "
        "Segment Builder expression editor."
    )
)
def generate_segment_logic(
    segment_description: str = Field(
        description=(
            "Plain-language description of the audience to build. "
            "Example: 'All customers in the US who made a purchase in the last 30 days "
            "and have opted in to email marketing.'"
        )
    ),
    dmo_filter: list[str] = Field(
        default=[],
        description=(
            "Optional: limit the schema scan to specific DMO API names. "
            "If empty, all DMOs are scanned (may be slow for large orgs)."
        ),
    ),
) -> str:
    if dmo_filter:
        dmo_list = [{"name": n, "displayName": n, "category": ""} for n in dmo_filter]
    else:
        dmo_list = list_objects(oauth_session, ENTITY_TYPE_DMO)

    schema_blocks = []
    for dmo in dmo_list:
        try:
            fields = get_fields_for_object(oauth_session, dmo["name"], ENTITY_TYPE_DMO)
            field_list = "\n".join(
                f"    - \"{f['name']}\" ({f.get('type', 'unknown')})" for f in fields
            )
            schema_blocks.append(f"### {dmo['name']} ({dmo.get('category', '')})\n{field_list}")
        except Exception as e:
            logger.warning(f"Could not fetch fields for {dmo['name']}: {e}")

    schema_text = "\n\n".join(schema_blocks)

    return (
        f"## Full data model schema\n{schema_text}\n\n"
        f"## Requested segment\n{segment_description}\n\n"
        "## Instructions for the AI assistant\n"
        "Write Data Cloud segment filter logic. Rules:\n"
        "- Primary object for segmentation is typically UnifiedIndividual__dlm\n"
        "- Use exact field API names from the schema above\n"
        "- Supported operators by type:\n"
        "    Text:    equals, not equals, contains, starts with, ends with, is null, is not null\n"
        "    Number:  equals, not equals, greater than, less than, >=, <=, between, is null\n"
        "    Date:    equals, before, after, between, in last N days/months, is null\n"
        "    Boolean: is true, is false, is null\n"
        "- Related object filters use: [RelatedObject__dlm].[FieldApiName]\n"
        "- Calculated Insight filters use: [InsightName__insight].[MeasureName]\n"
        "- For count-based rules (e.g. 'at least 2 orders'), use the "
        "  'Calculated Insights' or 'Related Attribute' filter type\n"
        "- Present filters as a structured list:\n"
        "    Object: <dmo_name>\n"
        "    Field: <field_api_name>\n"
        "    Operator: <operator>\n"
        "    Value: <value>\n"
        "- Combine conditions with AND / OR groups\n"
    )


# ---------------------------------------------------------------------------
# Query editor / troubleshooting
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Execute a SQL query against Data Cloud and return the results. "
        "Use this for troubleshooting data issues, validating field values, "
        "or testing calculated insight logic. "
        "SQL follows the PostgreSQL dialect — always double-quote identifiers "
        "and use exact casing. "
        "Before running a query, use list_data_model_objects / describe_data_model_object "
        "to verify available tables and columns."
    )
)
def query(
    sql: str = Field(
        description=(
            "A SQL query in the Data Cloud (PostgreSQL) dialect. "
            "Always double-quote identifiers and preserve exact casing. "
            "Example: SELECT \"Email__c\", COUNT(*) AS cnt "
            "FROM \"UnifiedIndividual__dlm\" GROUP BY \"Email__c\" LIMIT 100"
        )
    ),
    dataspace: str = Field(
        default="default",
        description="The Data Cloud dataspace to query against. Defaults to 'default'.",
    ),
) -> dict:
    return run_query(oauth_session, sql, dataspace=dataspace)


@mcp.tool(
    description=(
        "List all available tables visible in the Data Cloud query engine. "
        "This uses the system catalog and respects the DEFAULT_LIST_TABLE_FILTER env var. "
        "Useful as a quick sanity check for what's queryable."
    )
)
def list_tables() -> list[str]:
    sql = (
        "SELECT c.relname AS TABLE_NAME "
        "FROM pg_catalog.pg_namespace n, pg_catalog.pg_class c "
        "LEFT JOIN pg_catalog.pg_description d "
        "  ON (c.oid = d.objoid AND d.objsubid = 0 AND d.classoid = 'pg_class'::regclass) "
        "WHERE c.relnamespace = n.oid AND c.relname LIKE '%s'"
        % DEFAULT_LIST_TABLE_FILTER
    )
    result = run_query(oauth_session, sql)
    return [row[0] for row in result.get("data", [])]


@mcp.tool(
    description=(
        "Describe the columns of a table as seen by the Data Cloud query engine. "
        "Returns column names and data types via the pg_catalog system views."
    )
)
def describe_table(
    table: str = Field(description="The table name (API name with suffix, e.g. 'UnifiedIndividual__dlm')."),
) -> list[str]:
    sql = (
        "SELECT a.attname, t.typname "
        "FROM pg_catalog.pg_namespace n "
        "JOIN pg_catalog.pg_class c ON (c.relnamespace = n.oid) "
        "JOIN pg_catalog.pg_attribute a ON (a.attrelid = c.oid) "
        "JOIN pg_catalog.pg_type t ON (a.atttypid = t.oid) "
        "WHERE a.attnum > 0 AND NOT a.attisdropped "
        f"AND c.relname = '{table}'"
    )
    result = run_query(oauth_session, sql)
    return [f"{row[0]} ({row[1]})" for row in result.get("data", [])]


@mcp.tool(
    description=(
        "Write a targeted troubleshooting SQL query to diagnose a data quality or "
        "pipeline issue in Data Cloud. Inspect relevant tables first, then craft a "
        "query that reveals the problem (duplicates, nulls, mismatched keys, counts, etc.)."
    )
)
def troubleshoot_data(
    issue_description: str = Field(
        description=(
            "Describe the data problem to investigate. "
            "Example: 'Email addresses are appearing as null in the "
            "UnifiedIndividual__dlm after the CRM data stream ran.'"
        )
    ),
    table_names: list[str] = Field(
        default=[],
        description=(
            "Optional: table or DMO/DLO API names relevant to the issue. "
            "If provided, their schemas are fetched to help formulate an accurate query."
        ),
    ),
) -> str:
    schema_blocks = []
    for table in table_names:
        try:
            fields = get_fields_for_object(oauth_session, table)
            field_list = "\n".join(
                f"    - \"{f['name']}\" ({f.get('type', 'unknown')})" for f in fields
            )
            schema_blocks.append(f"### {table}\n{field_list}")
        except Exception:
            # Fall back to query engine catalog
            try:
                cols = describe_table(table)
                schema_blocks.append(f"### {table}\n" + "\n".join(f"    - {c}" for c in cols))
            except Exception as e:
                schema_blocks.append(f"### {table}\n    (Could not fetch schema: {e})")

    schema_text = "\n\n".join(schema_blocks) if schema_blocks else "(No tables specified)"

    return (
        f"## Relevant table schemas\n{schema_text}\n\n"
        f"## Issue to investigate\n{issue_description}\n\n"
        "## Instructions for the AI assistant\n"
        "Write one or more diagnostic SQL queries for the Data Cloud Query Editor. Rules:\n"
        "- Always double-quote identifiers\n"
        "- Use exact field names from the schema above\n"
        "- Diagnose the specific issue described above using targeted queries:\n"
        "    - NULL checks:  WHERE \"FieldName__c\" IS NULL\n"
        "    - Duplicates:   GROUP BY … HAVING COUNT(*) > 1\n"
        "    - Row counts:   SELECT COUNT(*) FROM …\n"
        "    - Value spread: SELECT \"FieldName__c\", COUNT(*) GROUP BY 1 ORDER BY 2 DESC\n"
        "    - Date range:   WHERE \"EventDate__c\" >= CURRENT_DATE - INTERVAL '7 days'\n"
        "- Add a plain-language explanation of what each query checks and what "
        "  the results would mean for the issue\n"
        "- Keep queries LIMIT 1000 unless a full count is required\n"
    )


# ---------------------------------------------------------------------------
# General Data Cloud Q&A
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Returns the resolved Salesforce and Data Cloud instance URLs being used "
        "by the current session. Useful for diagnosing auth or endpoint issues."
    )
)
def debug_auth() -> dict:
    """Show the actual SF and DC instance URLs in use."""
    sf_url = oauth_session.get_instance_url()
    dc_url = oauth_session.get_dc_instance_url()
    return {
        "sf_instance_url": sf_url,
        "dc_instance_url": dc_url,
        "dc_metadata_endpoint": f"{dc_url}/api/v1/metadata/",
    }


@mcp.tool(
    description=(
        "Answer general questions about Salesforce Data Cloud (Data 360): "
        "architecture, key concepts (DLO, DMO, Identity Resolution, Activation, "
        "Calculated Insights, Segments, Data Streams, Data Bundles, Data Graphs), "
        "setup, licensing, troubleshooting, and best practices. "
        "Use this when the user asks a conceptual or how-to question rather than "
        "requesting code generation."
    )
)
def datacloud_help(
    question: str = Field(
        description="The question about Salesforce Data Cloud to answer."
    ),
) -> str:
    return (
        f"## Question\n{question}\n\n"
        "## Instructions for the AI assistant\n"
        "Answer the question above about Salesforce Data Cloud (also called Data 360 "
        "as of Oct 2025). Draw on your knowledge of:\n"
        "- Core objects: Data Lake Objects (DLOs), Data Model Objects (DMOs), "
        "  Unified Individual / Unified Account, Calculated Insights, Segments\n"
        "- Data ingestion: Data Streams, Connectors (CRM, Marketing Cloud, "
        "  Ingestion API, MuleSoft, S3, etc.)\n"
        "- Identity Resolution: rulesets, match rules, reconciliation rules, "
        "  UnifiedIndividual__dlm, UnifiedLinkIndividual__dlm\n"
        "- Activation: Activation Targets, Activation Membership, Audience Splitting\n"
        "- Query: PostgreSQL dialect, Query API, Query Editor\n"
        "- Data Graphs and JSON bundles\n"
        "- Billing: credits model, ingestion vs query credits\n"
        "- Best practices for performance, data quality, and governance\n"
        "Keep the answer concise, accurate, and practical. "
        "If the question is about syntax, refer the user to the appropriate "
        "code-generation tool (generate_formula, generate_calculated_insight_sql, etc.).\n"
    )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger.info("Starting Salesforce Data Cloud MCP server")
    mcp.run()
