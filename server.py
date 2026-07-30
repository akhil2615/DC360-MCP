"""
Salesforce Data Cloud MCP Server
Provides Cursor with live access to your Data Cloud org metadata and query engine,
enabling AI-assisted authoring of formulas, streaming transforms, calculated insight SQL,
segment logic, and ad-hoc troubleshooting queries.
"""
import logging
import os
import re
from pathlib import Path

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
from dc_admin_api import (
    list_data_spaces as _list_data_spaces,
    list_data_sources as _list_data_sources,
    list_data_connectors as _list_data_connectors,
    list_data_streams as _list_data_streams,
    list_segments as _list_segments,
    list_batch_data_transforms as _list_batch_data_transforms,
    list_streaming_data_transforms as _list_streaming_data_transforms,
    list_activation_targets as _list_activation_targets,
    list_activations as _list_activations,
    list_identity_resolutions as _list_identity_resolutions,
    list_data_bundles as _list_data_bundles,
    get_org_inventory as _get_org_inventory,
    probe_endpoints as _probe_endpoints,
)
from datacloud_platform.ops_tools import build_ssot_path, safe_mutation, safe_read
from datacloud_platform.pipeline_tools import (
    deploy_check as _pipeline_deploy_check,
    retrieve_metadata as _pipeline_retrieve,
    run_git_diff_mode as _run_git_diff_mode,
)
from datacloud_platform.blueprint_tools import generate_blueprint_artifacts
from datacloud_platform.contracts import op_result

logger = logging.getLogger(__name__)

mcp = FastMCP("Salesforce Data Cloud")

sf_org: OAuthConfig = OAuthConfig.from_env()
oauth_session: OAuthSession = OAuthSession(sf_org)

DEFAULT_LIST_TABLE_FILTER = os.getenv("DEFAULT_LIST_TABLE_FILTER", "%")
# Allow only characters valid in a SQL LIKE pattern for table names so the
# value can be safely interpolated into the pg_catalog query in list_tables().
if not re.match(r"^[A-Za-z0-9_%]+$", DEFAULT_LIST_TABLE_FILTER):
    raise ValueError(
        f"Invalid DEFAULT_LIST_TABLE_FILTER: {DEFAULT_LIST_TABLE_FILTER!r}. "
        "Only letters, digits, underscore, and '%' are permitted."
    )

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
# Org inventory discovery — Data Spaces, Data Streams, Sources, Segments,
# Transforms, Activations, Identity Resolutions, Data Bundles
#
# These tools call the Salesforce Connect REST API and fall back to SOQL
# against the corresponding SObjects. Every function returns an envelope:
#   {category, count, source, records: [...], attempts: [...]}
# The attempts trail is useful when a category is empty — it shows which
# candidate endpoints/SObjects were tried and how each responded.
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "List all Data Spaces defined in the Data Cloud org. "
        "Returns each data space's name, display name, and id."
    )
)
def list_data_spaces() -> dict:
    return _list_data_spaces(oauth_session)


@mcp.tool(
    description=(
        "List all Data Sources (external systems that feed Data Cloud, e.g. "
        "S3, SFTP, Marketing Cloud, Snowflake, Core CRM). Distinct from "
        "Data Connectors, which are the configured connections."
    )
)
def list_data_sources() -> dict:
    return _list_data_sources(oauth_session)


@mcp.tool(
    description=(
        "List all Data Connectors — configured connections from Data Cloud "
        "to an external Data Source. Includes the connector type "
        "(S3, Ingestion API, Marketing Cloud, Snowflake, Salesforce CRM, etc.) "
        "and current status. This is what you use to understand which external "
        "systems the org is actually integrated with."
    )
)
def list_data_connectors() -> dict:
    return _list_data_connectors(oauth_session)


@mcp.tool(
    description=(
        "List all Data Streams in the given data space. Each stream ties a "
        "Data Connector + source object to a target DLO with a refresh mode. "
        "The primary discovery signal for what data is actively flowing in."
    )
)
def list_data_streams(
    dataspace: str = Field(
        default="default",
        description="Data Cloud data space; defaults to 'default'.",
    ),
) -> dict:
    return _list_data_streams(oauth_session, dataspace)


@mcp.tool(
    description=(
        "List all Segments defined in the given data space. Returns each "
        "segment's API name, display name, type (Standard / Rapid Publish / "
        "Real-time / Waterfall / Nested), publish status, and the DMO it "
        "segments on."
    )
)
def list_segments(
    dataspace: str = Field(
        default="default",
        description="Data Cloud data space; defaults to 'default'.",
    ),
) -> dict:
    return _list_segments(oauth_session, dataspace)


@mcp.tool(
    description=(
        "List all Batch Data Transforms in the given data space. "
        "Batch transforms run on a schedule and materialize into a target DLO/DMO."
    )
)
def list_batch_data_transforms(
    dataspace: str = Field(
        default="default",
        description="Data Cloud data space; defaults to 'default'.",
    ),
) -> dict:
    return _list_batch_data_transforms(oauth_session, dataspace)


@mcp.tool(
    description=(
        "List all Streaming Data Transforms in the given data space. "
        "Streaming transforms run in real-time as records arrive on a source "
        "Data Stream and write to a target DMO."
    )
)
def list_streaming_data_transforms(
    dataspace: str = Field(
        default="default",
        description="Data Cloud data space; defaults to 'default'.",
    ),
) -> dict:
    return _list_streaming_data_transforms(oauth_session, dataspace)


@mcp.tool(
    description=(
        "List all Activation Targets configured in the org — the downstream "
        "platforms Data Cloud can activate audiences to (Marketing Cloud, ad "
        "platforms, webhooks, cloud storage, etc.)."
    )
)
def list_activation_targets() -> dict:
    return _list_activation_targets(oauth_session)


@mcp.tool(
    description=(
        "List all Activations — mappings from a Segment to an Activation Target. "
        "Each activation is what actually pushes an audience out to the target."
    )
)
def list_activations(
    dataspace: str = Field(
        default="default",
        description="Data Cloud data space; defaults to 'default'.",
    ),
) -> dict:
    return _list_activations(oauth_session, dataspace)


@mcp.tool(
    description=(
        "List all Identity Resolution rulesets. Each ruleset defines how "
        "source records are matched and reconciled into a Unified object."
    )
)
def list_identity_resolutions() -> dict:
    return _list_identity_resolutions(oauth_session)


@mcp.tool(
    description=(
        "List all Data Bundles / Data Kits installed in the org. "
        "Bundles are pre-built packages of DLOs, DMOs, and mappings."
    )
)
def list_data_bundles() -> dict:
    return _list_data_bundles(oauth_session)


@mcp.tool(
    description=(
        "Roll-up: fetch EVERY inventory category in one call. Returns a single "
        "envelope with data spaces, sources, connectors, streams, segments, "
        "batch/streaming transforms, activations, targets, identity resolutions, "
        "and data bundles, plus a snapshot timestamp. Use this to feed a "
        "dashboard or architecture view. Never raises — partial failures show "
        "up in each category's 'attempts' trail."
    )
)
def list_org_inventory(
    dataspace: str = Field(
        default="default",
        description="Data Cloud data space; defaults to 'default'.",
    ),
) -> dict:
    return _get_org_inventory(oauth_session, dataspace)


@mcp.tool(
    description=(
        "Probe the org to find which Data Cloud REST endpoints and SObjects "
        "actually exist in your API version. Reports the HTTP status for every "
        "candidate resource and the record count for every candidate SObject. "
        "Run this ONCE against a new org before relying on list_org_inventory "
        "so you know which discovery paths will work."
    )
)
def probe_dc_admin_endpoints() -> dict:
    return _probe_endpoints(oauth_session)


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
        "- GROUP BY (with space) MUST use ALIAS names, NOT field references:\n"
        "  CORRECT: GROUP BY customer_id__c\n"
        "  WRONG:   GROUP BY UnifiedIndividual__dlm.ssot__Id__c\n"
        "- CRITICAL: Write the ENTIRE SQL as a SINGLE LINE — the CI builder parser\n"
        "  may split on line breaks and treat remaining text as invalid.\n"
        "- Put measures (aggregates) BEFORE dimensions in the SELECT list\n"
        "- Use IFNULL() for key qualifier matching in JOINs:\n"
        "  AND IFNULL(Table1.KQ_Field__c, '') = IFNULL(Table2.KQ_Field__c, '')\n"
        "- HAVING clause supported for filtering window function results:\n"
        "  HAVING RANK() OVER (ORDER BY SUM(amount)) < 1000\n"
        "- NO date functions in WHERE clause — date_add, CURRENT_DATE, CURRENT_TIMESTAMP,\n"
        "  INTERVAL are all rejected by the CI builder parser.\n"
        "  Use the CI Lookback Period setting in the UI instead.\n"
        "- Always web-search for current syntax when unsure before generating code\n\n"
        "### Template — Spend by Customer (MUST be a single line)\n"
        "SELECT SUM(ssot__SalesOrder__dlm.ssot__GrandTotalAmount__c) AS customer_spend__c, "
        "UnifiedIndividual__dlm.ssot__Id__c AS CustomerId__c "
        "FROM ssot__SalesOrder__dlm "
        "JOIN IndividualIdentityLink__dlm "
        "ON ssot__SalesOrder__dlm.ssot__SoldToCustomerId__c = IndividualIdentityLink__dlm.SourceRecordId__c "
        "AND IFNULL(ssot__SalesOrder__dlm.KQ_SoldToCustomerId__c, '') = IFNULL(IndividualIdentityLink__dlm.KQ_SourceRecordId__c, '') "
        "LEFT OUTER JOIN UnifiedIndividual__dlm "
        "ON IndividualIdentityLink__dlm.UnifiedRecordId__c = UnifiedIndividual__dlm.ssot__Id__c "
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
    import re
    if not re.match(r'^[A-Za-z0-9_]+$', table):
        raise ValueError(f"Invalid table name: '{table}'. Only alphanumeric characters and underscores allowed.")
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


# ---------------------------------------------------------------------------
# Operational API tools (FLASH-style admin surface with dry-run guardrails)
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Create a Data Lake Object via Data Cloud SSOT API. "
        "By default runs in dry-run mode and only returns the planned request."
    )
)
def create_dlo(
    request_body: dict = Field(
        description="Raw API payload for DLO create call under /ssot/data-lake-objects."
    ),
    dry_run: bool = Field(default=True, description="When true, only previews request without executing."),
) -> dict:
    return safe_mutation(
        oauth_session,
        action="create_dlo",
        method="POST",
        path=build_ssot_path("data-lake-objects"),
        body=request_body,
        dry_run=dry_run,
    )


@mcp.tool(description="Update a Data Lake Object by id with dry-run safeguards.")
def update_dlo(
    dlo_id: str = Field(description="DLO id to update."),
    request_body: dict = Field(description="Raw update payload."),
    dry_run: bool = Field(default=True, description="When true, preview only."),
) -> dict:
    return safe_mutation(
        oauth_session,
        action="update_dlo",
        method="PATCH",
        path=build_ssot_path(f"data-lake-objects/{dlo_id}"),
        body=request_body,
        dry_run=dry_run,
    )


@mcp.tool(description="Delete a Data Lake Object by id with dry-run safeguards.")
def delete_dlo(
    dlo_id: str = Field(description="DLO id to delete."),
    dry_run: bool = Field(default=True, description="When true, preview only."),
) -> dict:
    return safe_mutation(
        oauth_session,
        action="delete_dlo",
        method="DELETE",
        path=build_ssot_path(f"data-lake-objects/{dlo_id}"),
        dry_run=dry_run,
    )


@mcp.tool(description="Create a segment through Data Cloud SSOT API with dry-run safeguards.")
def create_segment(
    request_body: dict = Field(description="Raw segment payload for /ssot/segments."),
    dry_run: bool = Field(default=True, description="When true, preview only."),
) -> dict:
    return safe_mutation(
        oauth_session,
        action="create_segment",
        method="POST",
        path=build_ssot_path("segments"),
        body=request_body,
        dry_run=dry_run,
    )


@mcp.tool(description="Update a segment by id with dry-run safeguards.")
def update_segment(
    segment_id: str = Field(description="Segment id to update."),
    request_body: dict = Field(description="Raw update payload."),
    dry_run: bool = Field(default=True, description="When true, preview only."),
) -> dict:
    return safe_mutation(
        oauth_session,
        action="update_segment",
        method="PATCH",
        path=build_ssot_path(f"segments/{segment_id}"),
        body=request_body,
        dry_run=dry_run,
    )


@mcp.tool(description="Delete a segment by id with dry-run safeguards.")
def delete_segment(
    segment_id: str = Field(description="Segment id to delete."),
    dry_run: bool = Field(default=True, description="When true, preview only."),
) -> dict:
    return safe_mutation(
        oauth_session,
        action="delete_segment",
        method="DELETE",
        path=build_ssot_path(f"segments/{segment_id}"),
        dry_run=dry_run,
    )


@mcp.tool(description="Update an activation by id with dry-run safeguards.")
def update_activation(
    activation_id: str = Field(description="Activation id to update."),
    request_body: dict = Field(description="Raw update payload."),
    dry_run: bool = Field(default=True, description="When true, preview only."),
) -> dict:
    return safe_mutation(
        oauth_session,
        action="update_activation",
        method="PATCH",
        path=build_ssot_path(f"activations/{activation_id}"),
        body=request_body,
        dry_run=dry_run,
    )


@mcp.tool(description="Delete an activation by id with dry-run safeguards.")
def delete_activation(
    activation_id: str = Field(description="Activation id to delete."),
    dry_run: bool = Field(default=True, description="When true, preview only."),
) -> dict:
    return safe_mutation(
        oauth_session,
        action="delete_activation",
        method="DELETE",
        path=build_ssot_path(f"activations/{activation_id}"),
        dry_run=dry_run,
    )


@mcp.tool(description="Create or replace a DLO-DMO mapping with dry-run safeguards.")
def create_dlo_dmo_mapping(
    request_body: dict = Field(description="Raw mapping payload for /ssot/data-model-object-mappings."),
    dry_run: bool = Field(default=True, description="When true, preview only."),
) -> dict:
    return safe_mutation(
        oauth_session,
        action="create_dlo_dmo_mapping",
        method="POST",
        path=build_ssot_path("data-model-object-mappings"),
        body=request_body,
        dry_run=dry_run,
    )


@mcp.tool(description="Delete a DLO-DMO mapping by id with dry-run safeguards.")
def delete_dlo_dmo_mapping(
    mapping_id: str = Field(description="Mapping id to delete."),
    dry_run: bool = Field(default=True, description="When true, preview only."),
) -> dict:
    return safe_mutation(
        oauth_session,
        action="delete_dlo_dmo_mapping",
        method="DELETE",
        path=build_ssot_path(f"data-model-object-mappings/{mapping_id}"),
        dry_run=dry_run,
    )


@mcp.tool(description="Update a mapping by delete+create plan with dry-run safeguards.")
def update_dlo_dmo_mapping(
    mapping_id: str = Field(description="Existing mapping id to replace."),
    request_body: dict = Field(description="Replacement payload for create operation."),
    dry_run: bool = Field(default=True, description="When true, preview only."),
) -> dict:
    delete_plan = safe_mutation(
        oauth_session,
        action="update_dlo_dmo_mapping.delete_phase",
        method="DELETE",
        path=build_ssot_path(f"data-model-object-mappings/{mapping_id}"),
        dry_run=dry_run,
    )
    create_plan = safe_mutation(
        oauth_session,
        action="update_dlo_dmo_mapping.create_phase",
        method="POST",
        path=build_ssot_path("data-model-object-mappings"),
        body=request_body,
        dry_run=dry_run,
    )
    return op_result(
        action="update_dlo_dmo_mapping",
        summary="Generated two-phase mapping replacement result.",
        details={"delete_phase": delete_plan, "create_phase": create_plan},
        warnings=["This operation is modeled as delete + create to match platform behavior."],
    )


@mcp.tool(description="Create a data transform with dry-run safeguards.")
def create_data_transform(
    request_body: dict = Field(description="Raw payload for /ssot/data-transforms."),
    dry_run: bool = Field(default=True, description="When true, preview only."),
) -> dict:
    return safe_mutation(
        oauth_session,
        action="create_data_transform",
        method="POST",
        path=build_ssot_path("data-transforms"),
        body=request_body,
        dry_run=dry_run,
    )


@mcp.tool(description="Update a data transform by id with dry-run safeguards.")
def update_data_transform(
    transform_id: str = Field(description="Transform id to update."),
    request_body: dict = Field(description="Raw update payload."),
    dry_run: bool = Field(default=True, description="When true, preview only."),
) -> dict:
    return safe_mutation(
        oauth_session,
        action="update_data_transform",
        method="PUT",
        path=build_ssot_path(f"data-transforms/{transform_id}"),
        body=request_body,
        dry_run=dry_run,
    )


@mcp.tool(description="Delete a data transform by id with dry-run safeguards.")
def delete_data_transform(
    transform_id: str = Field(description="Transform id to delete."),
    dry_run: bool = Field(default=True, description="When true, preview only."),
) -> dict:
    return safe_mutation(
        oauth_session,
        action="delete_data_transform",
        method="DELETE",
        path=build_ssot_path(f"data-transforms/{transform_id}"),
        dry_run=dry_run,
    )


@mcp.tool(description="Get data transform run history by transform id.")
def get_data_transform_run_history(
    transform_id: str = Field(description="Transform id to inspect."),
) -> dict:
    return safe_read(
        oauth_session,
        action="get_data_transform_run_history",
        path=build_ssot_path(f"data-transforms/{transform_id}/runs"),
    )


@mcp.tool(description="List Data Graph definitions.")
def list_data_graphs() -> dict:
    return safe_read(oauth_session, "list_data_graphs", build_ssot_path("data-graphs"))


@mcp.tool(description="Create a Data Graph with dry-run safeguards.")
def create_data_graph(
    request_body: dict = Field(description="Raw payload for /ssot/data-graphs."),
    dry_run: bool = Field(default=True, description="When true, preview only."),
) -> dict:
    return safe_mutation(
        oauth_session,
        action="create_data_graph",
        method="POST",
        path=build_ssot_path("data-graphs"),
        body=request_body,
        dry_run=dry_run,
    )


@mcp.tool(description="Delete a Data Graph by id with dry-run safeguards.")
def delete_data_graph(
    graph_id: str = Field(description="Data graph id to delete."),
    dry_run: bool = Field(default=True, description="When true, preview only."),
) -> dict:
    return safe_mutation(
        oauth_session,
        action="delete_data_graph",
        method="DELETE",
        path=build_ssot_path(f"data-graphs/{graph_id}"),
        dry_run=dry_run,
    )


# ---------------------------------------------------------------------------
# Pipeline tools (org diff, retrieve, promote, deploy check)
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Compare metadata drift in one of three modes: branch-vs-branch, "
        "org-vs-branch, org-vs-org (folder-vs-folder)."
    )
)
def run_org_diff(
    mode: str = Field(description="One of: branch-vs-branch, org-vs-branch, org-vs-org."),
    left: str = Field(description="Left side branch or folder path."),
    right: str = Field(description="Right side branch or folder path."),
) -> dict:
    repo_root = Path(__file__).resolve().parent
    result = _run_git_diff_mode(mode, left, right, repo_root)
    return op_result(
        action="run_org_diff",
        summary="Diff command completed.",
        details=result,
        ok=result.get("exit_code", 1) in (0, 1),
        warnings=["Exit code 1 can be expected when differences are found."],
    )


@mcp.tool(description="Retrieve Salesforce metadata from an org alias using manifest.")
def pipeline_retrieve(
    org_alias: str = Field(description="Salesforce org alias configured in sf CLI."),
    manifest_path: str = Field(default="salesforce-app/manifest/package.xml", description="Path to manifest file."),
    dry_run: bool = Field(default=True, description="When true, preview only."),
) -> dict:
    repo_root = Path(__file__).resolve().parent
    return _pipeline_retrieve(repo_root, org_alias, manifest_path, dry_run)


@mcp.tool(description="Promote a branch by producing a merge plan.")
def pipeline_promote(
    source_branch: str = Field(description="Branch to promote from."),
    target_branch: str = Field(description="Branch to promote to."),
    dry_run: bool = Field(default=True, description="When true, returns command plan only."),
) -> dict:
    command = f"git checkout {target_branch} && git merge --no-ff {source_branch}"
    if dry_run:
        return op_result(
            action="pipeline_promote",
            summary="Dry run only. Promotion command not executed.",
            details={"command": command},
            warnings=["Set dry_run=false in your own shell flow after review."],
        )
    return op_result(
        action="pipeline_promote",
        summary="Execution in-process is intentionally blocked for safety.",
        details={"command": command},
        ok=False,
        warnings=["Run this command manually after PR and policy checks."],
    )


@mcp.tool(description="Run check-only deployment with Salesforce CLI.")
def pipeline_deploy_check(
    org_alias: str = Field(description="Salesforce org alias configured in sf CLI."),
    manifest_path: str = Field(default="salesforce-app/manifest/package.xml", description="Path to manifest file."),
    dry_run: bool = Field(default=True, description="When true, preview only."),
) -> dict:
    repo_root = Path(__file__).resolve().parent
    return _pipeline_deploy_check(repo_root, org_alias, manifest_path, dry_run)


# ---------------------------------------------------------------------------
# Blueprint tooling
# ---------------------------------------------------------------------------

@mcp.tool(
    description=(
        "Generate Data360 blueprint artifacts (JSON + standalone HTML) from local metadata. "
        "Useful for architecture documentation and reviews."
    )
)
def generate_blueprint(
    brand_name: str = Field(default="Data360", description="Brand label shown in the report."),
    metadata_root: str = Field(
        default="salesforce-app/force-app/main/default",
        description="Root directory containing Salesforce metadata.",
    ),
    output_dir: str = Field(
        default="artifacts/blueprints",
        description="Directory where generated JSON and HTML artifacts are written.",
    ),
) -> dict:
    base_dir = Path(__file__).resolve().parent
    meta_path = (base_dir / metadata_root).resolve()
    out_path = (base_dir / output_dir).resolve()
    if not meta_path.exists():
        return op_result(
            action="generate_blueprint",
            summary="Metadata path does not exist.",
            details={"metadata_root": str(meta_path)},
            ok=False,
        )
    return generate_blueprint_artifacts(meta_path, out_path, brand_name)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger.info("Starting Salesforce Data Cloud MCP server")
    mcp.run()
