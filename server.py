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
    get_raw_metadata,
    list_objects,
    _parse_display_name,
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
        "CI SQL uses table/field names directly (no double-quoting), "
        "all aliases must end with __c suffix, GROUP BY uses alias names, "
        "and the standard join path is DMO → IndividualIdentityLink__dlm → UnifiedIndividual__dlm. "
        "Inspects the relevant DMO schemas before generating."
    )
)
def generate_calculated_insight_sql(
    dmo_names: list[str] = Field(
        description=(
            "List of DMO API names to include in the insight, "
            "e.g. ['UnifiedIndividual__dlm', 'ssot__SalesOrder__dlm']. "
            "Obtain names from list_data_model_objects."
        )
    ),
    insight_description: str = Field(
        description=(
            "Plain-language description of what the insight should calculate. "
            "Example: 'Total lifetime spend per unified individual, "
            "segmented by product category.'"
        )
    ),
) -> str:
    schema_blocks = []
    for dmo in dmo_names:
        fields = get_fields_for_object(oauth_session, dmo, ENTITY_TYPE_DMO)
        field_list = "\n".join(
            f"    - {f['name']} ({f.get('type', 'unknown')})" for f in fields
        )
        schema_blocks.append(f"### {dmo}\n{field_list}")

    schema_text = "\n\n".join(schema_blocks)

    return (
        f"## DMO schemas\n{schema_text}\n\n"
        f"## Requested insight\n{insight_description}\n\n"
        "## Instructions for the AI assistant\n"
        "Write a valid Data Cloud Calculated Insight SQL statement.\n\n"
        "### CRITICAL CI SQL RULES\n"
        "- Use table/field names DIRECTLY — NO double-quoting needed\n"
        "- Table aliases supported: FROM ssot__SalesOrder__dlm S\n"
        "- All measure/dimension aliases MUST end with __c suffix:\n"
        "  CORRECT: SUM(amount) AS total_spend__c\n"
        "  WRONG:   SUM(amount) AS TotalSpend\n"
        "- Every SELECT must produce at least one MEASURE (aggregate) and one DIMENSION\n"
        "- GROUP BY uses the ALIAS name: GROUP BY CustomerId__c\n"
        "- String literals use SINGLE QUOTES: 'value'\n"
        "- Standard join path to unified profiles:\n"
        "  DMO → IndividualIdentityLink__dlm (SourceRecordId__c) → UnifiedIndividual__dlm (ssot__Id__c)\n\n"
        "### Supported functions\n"
        "- Aggregate: SUM(), COUNT(), AVG(), MIN(), MAX(), FIRST()\n"
        "- Window: ROW_NUMBER(), RANK(), DENSE_RANK(), NTILE() with OVER (ORDER BY ...)\n"
        "- Conditional: CASE WHEN ... THEN ... ELSE ... END\n"
        "- Date: CDPHour() for time dimensions\n"
        "- Subquery: NOT IN (subquery), inline views FROM (SELECT ...) AS alias\n"
        "- JOINs: INNER JOIN, LEFT JOIN, LEFT OUTER JOIN with ON clause\n\n"
        "### CI-SPECIFIC RULES (the CI builder has a stricter parser than Query Editor)\n"
        "- GROUP BY MUST use ALIAS names, NOT field references:\n"
        "  CORRECT: GROUP BY customer_id__c\n"
        "  WRONG:   GROUP BY UnifiedIndividual__dlm.ssot__Id__c\n"
        "- Put measures (aggregates) BEFORE dimensions in the SELECT list\n"
        "- Use IFNULL() for key qualifier matching in JOINs:\n"
        "  AND IFNULL(Table1.KQ_Field__c, '') = IFNULL(Table2.KQ_Field__c, '')\n"
        "- HAVING clause supported for filtering window function results:\n"
        "  HAVING RANK() OVER (ORDER BY SUM(amount)) < 1000\n"
        "- If date arithmetic (CURRENT_DATE - INTERVAL) fails in the CI builder,\n"
        "  use the Lookback Period setting in the CI UI instead\n"
        "- Always web-search for current syntax when unsure before generating code\n\n"
        "### Template — Spend by Customer\n"
        "SELECT\n"
        "    SUM(ssot__SalesOrder__dlm.ssot__GrandTotalAmount__c) AS customer_spend__c,\n"
        "    UnifiedIndividual__dlm.ssot__Id__c AS CustomerId__c\n"
        "FROM ssot__SalesOrder__dlm\n"
        "LEFT JOIN IndividualIdentityLink__dlm\n"
        "    ON ssot__SalesOrder__dlm.ssot__SoldToCustomerId__c = IndividualIdentityLink__dlm.SourceRecordId__c\n"
        "LEFT JOIN UnifiedIndividual__dlm\n"
        "    ON IndividualIdentityLink__dlm.UnifiedRecordId__c = UnifiedIndividual__dlm.ssot__Id__c\n"
        "GROUP BY CustomerId__c\n"
    )


@mcp.tool(
    description=(
        "Generate segment logic for a Data Cloud segment. "
        "Scans the full data model (DMOs and CIs) to suggest the correct "
        "Segment On entity, direct attributes, related attributes with containers, "
        "container paths, aggregations, and filter operators. "
        "Also checks for existing Calculated Insights that can simplify the segment."
    )
)
def generate_segment_logic(
    segment_description: str = Field(
        description=(
            "Plain-language description of the audience to build. "
            "Example: 'All customers in the US who made at least 2 purchases "
            "in the last 90 days with total spend > $500.'"
        )
    ),
    dmo_filter: list[str] = Field(
        default=[],
        description=(
            "Optional: limit the schema scan to specific DMO API names. "
            "If empty, all DMOs are scanned."
        ),
    ),
) -> str:
    if dmo_filter:
        dmo_list = [{"name": n, "displayName": n, "category": ""} for n in dmo_filter]
    else:
        dmo_list = list_objects(oauth_session, ENTITY_TYPE_DMO)

    ci_list = list_objects(oauth_session, ENTITY_TYPE_CI)

    schema_blocks = []
    for dmo in dmo_list:
        try:
            fields = get_fields_for_object(oauth_session, dmo["name"], ENTITY_TYPE_DMO)
            field_list = "\n".join(
                f"    - {f['name']} ({f.get('type', 'unknown')})" for f in fields
            )
            schema_blocks.append(f"### {dmo['name']}\n{field_list}")
        except Exception as e:
            logger.warning(f"Could not fetch fields for {dmo['name']}: {e}")

    schema_text = "\n\n".join(schema_blocks)

    ci_text = "\n".join(f"  - {ci['name']}" for ci in ci_list) if ci_list else "(none)"

    return (
        f"## Available DMOs\n{schema_text}\n\n"
        f"## Available Calculated Insights\n{ci_text}\n\n"
        f"## Requested segment\n{segment_description}\n\n"
        "## Instructions for the AI assistant\n"
        "Design a Data Cloud segment using the Segment Builder. "
        "Present the output as structured Segment Builder steps.\n\n"
        "### Segment design rules\n"
        "- Segment On: typically UnifiedIndividual__dlm (use Unified over raw for dedup)\n"
        "- Direct Attributes: 1:1 or N:1 fields on the Segment On entity\n"
        "- Related Attributes: 1:N DMOs go inside Containers with aggregation\n"
        "- Container Path: always choose the SHORTEST path; avoid cyclic paths\n"
        "- If an existing CI can simplify the logic, use it as a direct attribute\n"
        "- Merge containers with same path joined by OR into one container\n"
        "- Use nested operators (up to 5 levels) inside containers\n\n"
        "### Operator reference\n"
        "Text: Is Equal To, Is Not Equal To, Contains, Does Not Contain, "
        "Begins With, Exists As A Whole Word, Is In, Is Not In\n"
        "Number: Is Equal To, Is Not Equal To, Is Less Than, Is Less Than Or Equal To, "
        "Is Greater Than, Is Greater Than Or Equal To, Is Between, Is Not Between, No Value\n"
        "Date: Is On, Is Before, Is After, Is Between, Last N Days, Last N Months, "
        "Next N Days, Next N Months, Is Anniversary Of, Day Of Week, Day Of Month, "
        "This Year, Last Year, Next Year\n"
        "Boolean: Is True, Is Not True, Is False, Is Not False, Is Unknown, Is Not Unknown\n\n"
        "### Aggregation types (for containers)\n"
        "Count, Sum, Average, Min, Max — applied to related records\n\n"
        "### Output format\n"
        "Segment On: <entity>\n"
        "Type: Standard | Rapid Publish | Waterfall | Nested | Real-time | Einstein Lookalike\n\n"
        "Direct Attributes:\n"
        "  - Field: <api_name>\n"
        "    Operator: <operator>\n"
        "    Value: <value>\n\n"
        "Container N (Related: <dmo_name>):\n"
        "  Path: SegmentOn → ... → DMO\n"
        "  Aggregation: <type> of <field>\n"
        "  Operator: <operator>\n"
        "  Value: <value>\n"
        "  Filters:\n"
        "    - Field: <field>\n"
        "      Operator: <operator>\n"
        "      Value: <value>\n\n"
        "Logic: Container 1 AND/OR Container 2\n\n"
        "### Best practices to mention\n"
        "- Add Event Date Time filters on engagement containers\n"
        "- Use CIs for heavy metrics instead of in-segment computation\n"
        "- For waterfall segments, list the priority order\n"
    )


# ---------------------------------------------------------------------------
# Query editor / troubleshooting
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Execute a SQL query against Data Cloud and return the results. "
        "Use this for troubleshooting data issues, validating field values, "
        "or testing calculated insight logic. "
        "SQL uses table/field names directly — no double-quoting needed. "
        "Table aliases are supported. String literals use single quotes. "
        "Before running a query, use list_data_model_objects / describe_data_model_object "
        "to verify available tables and columns."
    )
)
def query(
    sql: str = Field(
        description=(
            "A SQL query in the Data Cloud (PostgreSQL) dialect. "
            "Use table/field names directly without double-quoting. "
            "Table aliases supported. String literals use single quotes. "
            "Example: SELECT ssot__Id__c, ssot__FirstName__c "
            "FROM ssot__Individual__dlm ORDER BY ssot__LastModifiedDate__c DESC LIMIT 100"
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
        "Write one or more diagnostic SQL queries for the Data Cloud Query Editor.\n\n"
        "### Query Editor SQL rules (different from streaming transforms!)\n"
        "- Use table/field names DIRECTLY — NO double-quoting needed\n"
        "- Table aliases are supported: FROM ssot__Individual__dlm a\n"
        "- Reference fields via alias: a.ssot__FirstName__c\n"
        "- String literals use SINGLE QUOTES: 'value'\n"
        "- JOINs: JOIN table ON condition\n"
        "- Subqueries in WHERE and FROM (inline views) are supported\n"
        "- Window functions: ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...)\n"
        "- Date arithmetic: column + interval '7 days'\n"
        "- Always add LIMIT 10000 max (>10K may crash the Query Editor UI)\n"
        "- Query timeout is 5 minutes\n"
        "- Comments (-- style) ARE allowed in Query Editor\n\n"
        "### Common diagnostic patterns\n"
        "- NULL checks:  WHERE ssot__FirstName__c IS NULL\n"
        "- Duplicates:   GROUP BY field HAVING COUNT(*) > 1\n"
        "- Row counts:   SELECT COUNT(*) FROM table\n"
        "- Value spread: SELECT field, COUNT(*) AS cnt FROM table GROUP BY 1 ORDER BY 2 DESC\n"
        "- Date range:   WHERE ssot__CreatedDate__c >= CURRENT_DATE - INTERVAL '7 days'\n"
        "- Latest per group: ROW_NUMBER() OVER (PARTITION BY key ORDER BY date DESC)\n\n"
        "### Key DMO join paths\n"
        "- Individual → Email: ssot__Individual__dlm.ssot__Id__c = ssot__ContactPointEmail__dlm.ssot__PartyId__c\n"
        "- Individual → Phone: ssot__Individual__dlm.ssot__Id__c = ssot__ContactPointPhone__dlm.ssot__PartyId__c\n"
        "- Individual → Address: ssot__Individual__dlm.ssot__Id__c = ssot__ContactPointAddress__dlm.ssot__PartyId__c\n"
        "- Unified Link → Individual: IndividualIdentityLink__dlm.SourceRecordId__c = ssot__Individual__dlm.ssot__Id__c\n"
        "- Unified Link → Unified Individual: IndividualIdentityLink__dlm.UnifiedRecordId__c = UnifiedIndividual__dlm.ssot__Id__c\n\n"
        "- Add a plain-language explanation of what each query checks\n"
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
        "  UnifiedIndividual__dlm, IndividualIdentityLink__dlm\n"
        "- Activation: Activation Targets, Activation Membership, Audience Splitting\n"
        "- Query: PostgreSQL dialect, Query API, Query Editor\n"
        "- Data Graphs and JSON bundles\n"
        "- Billing: credits model, ingestion vs query credits\n"
        "- Best practices for performance, data quality, and governance\n"
        "Keep the answer concise, accurate, and practical. "
        "If the question is about syntax, refer the user to the appropriate "
        "code-generation tool (generate_formula, generate_calculated_insight_sql, etc.).\n"
    )


# ---------------------------------------------------------------------------
# DLO field export & DMO relationship export
# ---------------------------------------------------------------------------

def _extract_display(raw: str) -> str:
    return _parse_display_name(raw)

def _extract_category(raw: str) -> str:
    if not raw or not isinstance(raw, str):
        return ""
    try:
        import json as _json
        parsed = _json.loads(raw)
        if isinstance(parsed, dict):
            return parsed.get("entityCategory", "")
    except Exception:
        pass
    return ""


@mcp.tool(
    description=(
        "Export all fields of a Data Lake Object in a structured format suitable "
        "for documentation. Returns each field with: DLO name, DLO category, "
        "field display name, field API name, and data type. "
        "Use this when the user asks to document or list DLO fields."
    )
)
def export_dlo_fields(
    dlo_name: str = Field(description="Full API name of the DLO, e.g. 'Lead_Home__dll'."),
) -> str:
    raw = get_raw_metadata(oauth_session, entity_type=ENTITY_TYPE_DLO, entity_name=dlo_name)
    if not raw:
        fields = get_fields_for_object(oauth_session, dlo_name, ENTITY_TYPE_DLO)
        dlo_display = dlo_name
        dlo_category = ""
    else:
        entity = raw[0]
        fields = entity.get("fields", [])
        dlo_display = _extract_display(entity.get("displayName", dlo_name))
        dlo_category = _extract_category(entity.get("displayName", ""))

    header = "Data Lake Object Name\tData Lake Object Category\tDLO Field Name\tDLO Field API Name\tData Type"
    rows = [header]
    for f in fields:
        fname = f.get("name", "")
        fdisplay = _extract_display(f.get("displayName", fname))
        ftype = f.get("type", "unknown")
        rows.append(f"{dlo_display}\t{dlo_category}\t{fdisplay}\t{fname}\t{ftype}")

    return "\n".join(rows)


@mcp.tool(
    description=(
        "Export all fields of a Data Model Object in a structured format suitable "
        "for documentation. Returns each field with: DMO name, DMO API name, DMO category, "
        "DMO type (Standard/Custom), field display name, field API name, data type, "
        "and whether the field is a primary key. "
        "Use this when the user asks to document or list DMO fields."
    )
)
def export_dmo_fields(
    dmo_name: str = Field(description="Full API name of the DMO, e.g. 'ssot__Lead__dlm'."),
) -> str:
    raw = get_raw_metadata(oauth_session, entity_type=ENTITY_TYPE_DMO, entity_name=dmo_name)
    if not raw:
        fields = get_fields_for_object(oauth_session, dmo_name, ENTITY_TYPE_DMO)
        dmo_display = dmo_name
        dmo_category = ""
        primary_keys = []
    else:
        entity = raw[0]
        fields = entity.get("fields", [])
        dmo_display = _extract_display(entity.get("displayName", dmo_name))
        dmo_category = _extract_category(entity.get("displayName", ""))
        primary_keys = [pk.get("name", "") for pk in entity.get("primaryKeys", [])]

    dmo_type = "Standard" if dmo_name.startswith("ssot__") else "Custom"

    header = "DMO Name\tDMO API Name\tDMO Category\tDMO Type\tDMO Field Name\tDMO Field API Name\tDMO Field Data Type\tPrimary Key"
    rows = [header]
    for f in fields:
        fname = f.get("name", "")
        fdisplay = _extract_display(f.get("displayName", fname))
        ftype = f.get("type", "unknown")
        is_pk = "Yes" if fname in primary_keys else ""
        rows.append(f"{dmo_display}\t{dmo_name}\t{dmo_category}\t{dmo_type}\t{fdisplay}\t{fname}\t{ftype}\t{is_pk}")

    return "\n".join(rows)


@mcp.tool(
    description=(
        "Export the full DLO-to-DMO field mapping for a given Data Lake Object. "
        "Returns a tab-separated table with columns: "
        "Data Lake Object Name, Data Lake Object Category, DLO Field Name, "
        "DLO Field API Name, Data Type, DMO Name, DMO API Name, DMO Field Name, "
        "DMO Field API Name, DMO Field Data Type, DMO Type, DMO Category, "
        "Primary Key/Engagement Date, Custom Field. "
        "The AI assistant MUST fill in the DMO mapping columns based on "
        "Data Cloud standard mapping conventions and save it as a CSV/Excel file. "
        "Call list_data_model_objects and describe relevant DMOs to verify mappings."
    )
)
def export_dlo_to_dmo_mapping(
    dlo_name: str = Field(description="Full API name of the DLO, e.g. 'Lead_Home__dll'."),
) -> str:
    raw = get_raw_metadata(oauth_session, entity_type=ENTITY_TYPE_DLO, entity_name=dlo_name)
    if not raw:
        fields = get_fields_for_object(oauth_session, dlo_name, ENTITY_TYPE_DLO)
        dlo_display = dlo_name
        dlo_category = ""
    else:
        entity = raw[0]
        fields = entity.get("fields", [])
        dlo_display = _extract_display(entity.get("displayName", dlo_name))
        dlo_category = _extract_category(entity.get("displayName", ""))

    header = (
        "Data Lake Object Name\tData Lake Object Category\t"
        "DLO Field Name\tDLO Field API Name\tData Type\t"
        "DMO Name\tDMO API Name\tDMO Field Name\tDMO Field API Name\t"
        "DMO Field Data Type\tDMO Type\tDMO Category\t"
        "Primary Key/Engagement Date\tCustom Field"
    )
    rows = [header]
    for f in fields:
        fname = f.get("name", "")
        fdisplay = _extract_display(f.get("displayName", fname))
        ftype = f.get("type", "unknown")
        is_custom = "Yes" if not fname.startswith("ssot__") and not fname.startswith("cdp_sys_") and not fname.startswith("KQ_") else ""
        rows.append(
            f"{dlo_display}\t{dlo_category}\t{fdisplay}\t{fname}\t{ftype}\t"
            f"\t\t\t\t\t\t\t\t{is_custom}"
        )

    return (
        "## DLO fields exported\n"
        "The DLO field columns are populated. The DMO mapping columns are blank.\n\n"
        "## Instructions for the AI assistant\n"
        "1. Call list_data_model_objects to get all DMOs in the org\n"
        "2. Based on Data Cloud standard mapping conventions, fill in the DMO columns "
        "for each DLO field:\n"
        "   - Lead fields → ssot__Lead__dlm\n"
        "   - Name fields (FirstName, LastName, Name) → ssot__Individual__dlm\n"
        "   - Email fields → ssot__ContactPointEmail__dlm\n"
        "   - Phone fields → ssot__ContactPointPhone__dlm\n"
        "   - Address fields → ssot__ContactPointAddress__dlm\n"
        "   - System/IR fields → leave DMO columns blank\n"
        "3. Save the result as a .csv file in the project directory\n"
        "4. NEVER add comments in the CSV data\n"
        "5. Use the exact header format provided\n\n"
        f"## Data\n{chr(10).join(rows)}\n"
    )


@mcp.tool(
    description=(
        "Export DMO-to-DMO relationships from the metadata API. "
        "Returns a tab-separated table with columns: "
        "DMO Object, DMO Field, Key Qualifier (Field), Cardinality, "
        "Related DMO Object, Related DMO Field, Key Qualifier (Related Field). "
        "Use this when the user asks about DMO relationships, data model diagrams, "
        "or how DMOs connect to each other."
    )
)
def export_dmo_relationships(
    dmo_names: list[str] = Field(
        default=[],
        description=(
            "List of DMO API names to get relationships for. "
            "If empty, fetches all DMOs and their relationships."
        ),
    ),
) -> str:
    if dmo_names:
        dmo_list = dmo_names
    else:
        all_dmos = list_objects(oauth_session, ENTITY_TYPE_DMO)
        dmo_list = [d["name"] for d in all_dmos]

    header = (
        "DMO Object\tDMO Field\tKey Qualifier (Field)\t"
        "Cardinality\tRelated DMO Object\tRelated DMO Field\t"
        "Key Qualifier (Related Field)"
    )
    rows = [header]

    for dmo_name in dmo_list:
        try:
            raw = get_raw_metadata(oauth_session, entity_type=ENTITY_TYPE_DMO, entity_name=dmo_name)
            if not raw:
                continue
            entity = raw[0]
            dmo_display = _extract_display(entity.get("displayName", dmo_name))

            relationships = entity.get("relationships", [])
            for rel in relationships:
                rel_entity = rel.get("relatedEntity", "")
                rel_field = rel.get("relatedField", "")
                from_field = rel.get("fromField", rel.get("field", ""))
                cardinality = rel.get("cardinality", rel.get("relationshipType", ""))
                kq_field = rel.get("keyQualifierField", "")
                kq_related = rel.get("relatedKeyQualifierField", "")
                rows.append(
                    f"{dmo_display}\t{from_field}\t{kq_field}\t"
                    f"{cardinality}\t{rel_entity}\t{rel_field}\t{kq_related}"
                )

            for f in entity.get("fields", []):
                kq = f.get("keyQualifier", "")
                if kq:
                    fname = f.get("name", "")
                    fdisplay = _extract_display(f.get("displayName", fname))
                    rows.append(
                        f"{dmo_display}\t{fname}\t{kq}\t"
                        f"\t\t\t"
                    )
        except Exception as e:
            logger.warning(f"Could not fetch relationships for {dmo_name}: {e}")

    return "\n".join(rows)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger.info("Starting Salesforce Data Cloud MCP server")
    mcp.run()
