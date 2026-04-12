---
name: salesforce-datacloud
description: >-
  Salesforce Data Cloud (Data 360) expert skill. Use when the user mentions Data Cloud,
  Data 360, DLO, DMO, Calculated Insights, data streams, segments, streaming transforms,
  formula fields, identity resolution, activation, or asks for help troubleshooting
  Data Cloud data. Provides syntax rules, workflow guidance, and uses the datacloud
  MCP server tools to fetch live org metadata before generating code.
---

# Salesforce Data Cloud Expert

Connects to the user's org via the `datacloud` MCP tools to fetch live schemas,
then generates syntactically valid Data Cloud code.

## Auth architecture (two-step — do not skip)

```
1. Browser OAuth2 PKCE  →  SF access_token  +  sf_instance_url
   POST {loginUrl}/services/oauth2/token
   Scopes: api, cdp_query_api, cdp_profile_api, cdp_ingest_api

2. DC token exchange  →  DC access_token  +  c360a_url (scheme://host only)
   POST {sf_instance_url}/services/a360/token
   grant_type         = urn:salesforce:grant-type:external:cdp
   subject_token      = <SF access_token>
   subject_token_type = urn:ietf:params:oauth:token-type:access_token

SF token  → used for Connect REST API  (/services/data/v63.0/ssot/...)
DC token  → used for Data Cloud Direct API  ({c360a_url}/api/v1/...)
```

## API endpoints reference (from official Postman collection)

| API | Base URL | Token |
|-----|----------|-------|
| Query SQL | `{sf_instance_url}/services/data/v63.0/ssot/query-sql` | SF token |
| Metadata | `{c360a_url}/api/v1/metadata/` | DC token |
| Data Graph metadata | `{c360a_url}/api/v1/dataGraph/metadata/` | DC token |
| Profile read | `{c360a_url}/api/v1/profile/...` | DC token |
| Ingest (streaming) | `{c360a_url}/api/v1/ingest/sources/{connector}/{object}` | DC token |

**Important**: Always strip path components from the c360a URL — use `scheme://host` only.

## Workflow by task type

### 1. Formula fields (Data Streams)

1. Call `list_data_lake_objects` → identify the right DLO
2. Call `describe_data_lake_object(dlo_name)` → get field **labels** and types
3. Call `generate_formula(dlo_name, description)` → receive field context + rules
4. Write the formula using **only** the returned field **labels** (display names)

**Syntax rules:**
- CRITICAL: Reference source fields by **LABEL (display name)**, NOT API name:
  - Correct: `sourceField['Email']`
  - WRONG: `sourceField['Email__c']`
- CRITICAL: `AND` / `OR` are **infix operators**, NOT functions:
  - Correct: `(sourceField['Country'] == "US") OR (sourceField['Country'] == "USA")`
  - WRONG: `OR(sourceField['Country'] == "US", sourceField['Country'] == "USA")`
- String values use **double quotes**: `sourceField['Email'] == "test@test.com"`
- Branching: `IF(condition, trueValue, falseValue)` — nestable
- Null: use the keyword `null`
- String: `LEFT`, `RIGHT`, `MID`, `SUBSTITUTE`, `TRIM`, `UPPER`, `LOWER`,
  `LEN`, `EXTRACT`, `PROPER`
- Date: `PARSEDATE`, `DATE`, `DATEDIFF`, `DAYPRECISION`, `NOW()`, `TODAY()`
- Type: `NUMBER`, `TEXT`, `MD5`, `ABS`

For more patterns see [dc-syntax-reference.md](dc-syntax-reference.md).

---

### 2. Streaming transforms (Data Streams)

1. Call `describe_data_lake_object(source_dlo)` — source fields
2. Call `describe_data_model_object(target_dmo)` — target fields
3. Call `generate_streaming_transform(source, target, description)`
4. Write a SQL SELECT query with dot notation

**Syntax rules (different from formula fields!):**
- CRITICAL: Reference fields with **DOT NOTATION**: `DLOFullName.FieldName`
  - Example: `Lead_Home__dll.Email__c` (NOT `sourceField['Email']`)
  - Use the **full DLO API name** including the `__dll` suffix
- EVERY field MUST have an explicit **AS alias**, even pass-throughs:
  - Correct: `Lead_Home__dll.Email__c AS Email__c`
  - Wrong: `Lead_Home__dll.Email__c` (bare, no alias)
- FROM clause: `FROM Lead_Home__dll` (full name)
- String literals use **single quotes**: `'Mobile'`, `'USA'`
  - Double quotes are for identifiers/aliases only
- Null checks: `ISNOTNULL(DLO.Field)`, `ISNULL(DLO.Field)`, not-equal: `<>`
- Conditional: `CASE WHEN … THEN … ELSE … END`
- Supported: `CONCAT()`, `LOWER()`, `UPPER()`, `TRIM()`, `LENGTH()`,
  `SUBSTRING()`, `REPLACE()`, `REGEXP_REPLACE()`, `COALESCE()`, `CAST()`
- **NOT supported**: `LEFT()`, `RIGHT()`, `MID()`, `FIND()`
  - Use `SUBSTRING(text, start, length)` instead of `LEFT(text, n)`
- Set operations: `UNION`, `UNION ALL`
- JOINs: `INNER JOIN`, `LEFT JOIN`, `RIGHT JOIN`, `FULL OUTER JOIN` with `ON`
- WHERE: supported for filtering records
- **NEVER add SQL comments** (`--` or `/* */`)

**Template:**
```sql
SELECT
    Contact_core__dll.CustomerId AS CustomerId,
    CONCAT(Contact_core__dll.CustomerId, '_Mobile') AS PhoneId,
    Contact_core__dll.MobilePhone AS PhoneNumber,
    'Mobile' AS PhoneType
FROM Contact_core__dll
WHERE ISNOTNULL(Contact_core__dll.MobilePhone) AND Contact_core__dll.MobilePhone <> ''
```

---

### 3. Calculated Insights

Calculated Insights can be created via **Visual Builder** (low-code) or **SQL Editor**.
They produce **measures** (numeric aggregates) and **dimensions** (grouping keys).

**Creation methods:**
1. **Visual Builder** — drag-and-drop: select object → join related objects → add aggregate → define measures + dimensions → publish
2. **SQL Editor** — write SQL directly (syntax below)
3. **Streaming Insights** — real-time, 5-minute aggregation windows
4. **Data-Kits** — pre-built packages

**Workflow for SQL-based CI:**
1. Call `list_data_model_objects` → identify tables
2. Call `describe_data_model_object` for each table involved
3. Call `generate_calculated_insight_sql(dmo_names, description)`
4. Write SQL following these rules exactly

**CI SQL syntax rules (different from Query Editor and Streaming Transforms!):**
- Table/field names used directly — NO double-quoting needed
- Standard SQL dot notation (Table.Field) is fine for disambiguation in JOINs
- Table aliases supported: `FROM ssot__SalesOrder__dlm` or `ssot__SalesOrder__dlm S`
- All aliases for measures/dimensions MUST end with `__c` suffix
- Every SELECT must produce at least one **measure** (aggregate) and one **dimension**
- Every non-aggregate column in SELECT → must be in GROUP BY
- GROUP BY uses the alias name: `GROUP BY CustomerId__c`
- Aggregate functions: `SUM()`, `COUNT()`, `AVG()`, `MIN()`, `MAX()`, `FIRST()`
- Window functions: `ROW_NUMBER()`, `RANK()`, `DENSE_RANK()`, `NTILE()` with `OVER (ORDER BY ...)`
- Subqueries in FROM supported (inline views with `AS` alias)
- `NOT IN (subquery)` and `WHERE` subqueries supported
- CASE WHEN supported for bucketing/scoring
- `CDPHour()` function for time-period dimensions
- JOINs: INNER JOIN, LEFT JOIN, LEFT OUTER JOIN — use `ON` clause
- The standard join path to unified profiles:
  `DMO → IndividualIdentityLink__dlm → UnifiedIndividual__dlm`
- **GROUP BY** (with space) MUST use **alias names**, NOT field references:
  - Correct: `GROUP BY customer_id__c`
  - Wrong: `GROUP BY UnifiedIndividual__dlm.ssot__Id__c`
- CRITICAL: Write the **entire CI SQL as a single line** — the CI builder parser
  may split on line breaks and treat remaining text as invalid
- Put **measures (aggregates) BEFORE dimensions** in the SELECT list
- Use **IFNULL()** for key qualifier matching in JOINs:
  `AND IFNULL(Table1.KQ_Field__c, '') = IFNULL(Table2.KQ_Field__c, '')`
- **HAVING** clause supported for window function filtering:
  `HAVING RANK() OVER (ORDER BY SUM(amount)) < 1000`
- **NO date functions in WHERE** — `date_add()`, `CURRENT_DATE`, `CURRENT_TIMESTAMP`,
  `INTERVAL` are all rejected by the CI builder parser.
  Use the CI **Lookback Period** setting in the UI instead
- Non-aggregate filters (e.g. name IS NOT NULL) — may need to be handled in the
  **Segment** on top of the CI if the CI builder rejects them
- **Always verify syntax** by searching official docs before generating CI SQL

**Template — Spend by Customer (single line — required by CI builder):**
```sql
SELECT SUM(ssot__SalesOrder__dlm.ssot__GrandTotalAmount__c) AS customer_spend__c, UnifiedIndividual__dlm.ssot__Id__c AS CustomerId__c FROM ssot__SalesOrder__dlm JOIN IndividualIdentityLink__dlm ON ssot__SalesOrder__dlm.ssot__SoldToCustomerId__c = IndividualIdentityLink__dlm.SourceRecordId__c AND IFNULL(ssot__SalesOrder__dlm.KQ_SoldToCustomerId__c, '') = IFNULL(IndividualIdentityLink__dlm.KQ_SourceRecordId__c, '') LEFT OUTER JOIN UnifiedIndividual__dlm ON IndividualIdentityLink__dlm.UnifiedRecordId__c = UnifiedIndividual__dlm.ssot__Id__c GROUP BY CustomerId__c
```

**Common CI use cases:** LTV, RFM scoring, email engagement buckets,
customer rank by spend, website engagement score, social channel affinity.
See [dc-syntax-reference.md](dc-syntax-reference.md) for full examples.

---

### 4. Segments

When a user asks for a segment, scan the full data model (DLOs, DMOs, CIs) first.

**Workflow:**
1. Call `list_data_model_objects` → understand available DMOs
2. Call `list_calculated_insights` → check for existing CIs that can simplify the segment
3. Call `describe_data_model_object` for relevant DMOs
4. Call `generate_segment_logic(description, dmo_filter)` → live schema + rules
5. Present the result as structured Segment Builder instructions

**Segment types:**
- **Standard** — static criteria, refreshed on schedule
- **Rapid Publish** — near-instant output for Marketing Cloud activation
- **Waterfall** — hierarchical priority (drag-and-drop individual segments)
- **Nested** — include/exclude one segment from another (membership or definition mode)
- **Real-time** — updates dynamically as data flows in
- **Einstein Lookalike** — AI finds similar audience to a seed segment

**Key concepts:**
- **Segment On entity** — the DMO you segment on (usually `UnifiedIndividual__dlm`)
  - Use Unified objects over raw Individual for deduplication and better performance
- **Direct Attributes** — 1:1 fields on the Segment On entity (e.g. FirstName)
- **Related Attributes** — 1:N related DMOs (e.g. purchases, engagements)
  - Placed inside **Containers** with aggregation and filters
- **Container Path** — the join path from Segment On to the related DMO
  - Always choose the **shortest path** — avoid cyclic paths (a→b→c→a)
- **Container Aggregation** — Count, Sum, Average, Min, Max on related records
- **Nested Operators** — up to 5 levels of AND/OR nesting inside one container
- **Engagement data lookback** — default 2 years (standard), 7 days (rapid)
  - Add explicit Event Date filters to improve performance

**Operator reference by type:**

| Field type | Operators |
|-----------|-----------|
| Text | Is Equal To, Is Not Equal To, Contains, Does Not Contain, Begins With, Exists As A Whole Word, Is In, Is Not In |
| Number | Is Equal To, Is Not Equal To, Is Less Than, Is Less Than Or Equal To, Is Greater Than, Is Greater Than Or Equal To, Is Between, Is Not Between, No Value |
| Date | Is On, Is Before, Is After, Is Between, Last/Next N Days, Last/Next N Months, Is Anniversary Of, Day Of Week, Day Of Month, This Year, Last Year, Next Year |
| Boolean | Is True, Is Not True, Is False, Is Not False, Is Unknown, Is Not Unknown |

**Output format — present as Segment Builder steps:**
```
Segment On: UnifiedIndividual__dlm
Type: Standard

Direct Attributes:
  - Field: ssot__FirstName__c
    Operator: Is Not Equal To
    Value: NULL

Container 1 (Related: ssot__SalesOrder__dlm):
  Path: UnifiedIndividual__dlm → IndividualIdentityLink__dlm → ssot__SalesOrder__dlm
  Aggregation: Count
  Operator: Is Greater Than Or Equal To
  Value: 2
  Filter:
    - Field: ssot__PurchaseOrderDate__c
      Operator: Last 90 Days

Container 2 (Related: ssot__ContactPointEmail__dlm):
  Path: UnifiedIndividual__dlm → IndividualIdentityLink__dlm → ssot__Individual__dlm → ssot__ContactPointEmail__dlm
  Filter:
    - Field: ssot__EmailAddress__c
      Operator: Is Not Equal To
      Value: (empty)

Logic: Container 1 AND Container 2
```

**Best practices:**
- Use CIs for complex pre-computed metrics (LTV, RFM scores) instead of heavy in-segment logic
- Merge containers with same path joined by OR into one container with OR filters inside
- Use nested operators (up to 5 levels) instead of multiple containers
- Use nested segments in membership mode (not definition mode) for better performance
- Filter engagement data by Event Date Time to reduce data volume
- Avoid cyclic container paths — they cause timeouts and failures

For full operator details see [dc-syntax-reference.md](dc-syntax-reference.md).

---

### 5. Troubleshooting queries (Query Editor)

1. Call `troubleshoot_data(issue_description, table_names)` → schema + diagnostic rules
2. Write targeted queries using **Query Editor SQL syntax** (different from Calculated Insights)

**Query Editor SQL rules:**
- Table/field names used directly — NO double-quoting needed
- Table aliases supported: `FROM ssot__Individual__dlm a`
- Fields via alias: `a.ssot__FirstName__c`
- String literals: single quotes `'value'`
- JOINs: `JOIN table ON condition`
- Subqueries and window functions supported
- Date math: `column + interval '9 hour'`
- Comments allowed (`--` style)
- Always add `LIMIT 10000` max (>10K may crash the UI)
- Query timeout: 5 minutes

Common patterns:
```sql
SELECT COUNT(*) FROM ssot__Individual__dlm WHERE ssot__FirstName__c IS NULL

SELECT a.ssot__Id__c AS Id, a.ssot__FirstName__c AS FirstName,
    b.ssot__EmailAddress__c AS Email
FROM ssot__Individual__dlm a
LEFT JOIN ssot__ContactPointEmail__dlm b
    ON a.ssot__Id__c = b.ssot__PartyId__c
ORDER BY a.ssot__LastModifiedDate__c DESC
LIMIT 10
```

For full query templates see [dc-syntax-reference.md](dc-syntax-reference.md).

---

---

### 6. Documenting DLO fields, DMO fields, and mappings

When the user asks to list, document, or export fields or mappings:

**DLO fields only:**
1. Call `export_dlo_fields(dlo_name)` → returns tab-separated data
2. Save as .csv file with these headers:

```
Data Lake Object Name	Data Lake Object Category	DLO Field Name	DLO Field API Name	Data Type
```

**DMO fields only:**
1. Call `export_dmo_fields(dmo_name)` → returns tab-separated data
2. Save as .csv file with these headers:

```
DMO Name	DMO API Name	DMO Category	DMO Type	DMO Field Name	DMO Field API Name	DMO Field Data Type	Primary Key
```

**DLO-to-DMO mapping export:**
1. Call `export_dlo_to_dmo_mapping(dlo_name)` → returns DLO fields with blank DMO columns
2. Call `list_data_model_objects` and `describe_data_model_object` for relevant DMOs
3. Fill in the DMO mapping columns based on standard Data Cloud conventions
4. Save as .csv file with these headers:

```
Data Lake Object Name	Data Lake Object Category	DLO Field Name	DLO Field API Name	Data Type	DMO Name	DMO API Name	DMO Field Name	DMO Field API Name	DMO Field Data Type	DMO Type	DMO Category	Primary Key/Engagement Date	Custom Field
```

**DMO-to-DMO relationships:**
1. Call `export_dmo_relationships(dmo_names)` → returns relationship data
2. Save as .csv file with these headers:

```
DMO Object	DMO Field	Key Qualifier (Field)	Cardinality	Related DMO Object	Related DMO Field	Key Qualifier (Related Field)
```

**Rules for all exports:**
- NEVER add comments in CSV data
- Use tab-separated format for the tool output, convert to comma-separated for .csv files
- Always save the file to the project directory

---

## General Q&A

For conceptual questions (identity resolution, activation, data bundles, billing, etc.)
call `datacloud_help(question)` — it will answer using current Data Cloud knowledge.

## Debugging auth/endpoint issues

Call `debug_auth()` to see the resolved SF instance URL, DC c360a URL, and the
exact metadata endpoint being used. This helps diagnose 404s or connection errors.

## Code generation responsibility

Before generating ANY code (formula, streaming transform, CI SQL, query, segment logic):

1. **Verify field names** — call describe_data_lake_object or describe_data_model_object first
2. **Verify syntax** — check dc-syntax-reference.md rules for the specific feature
3. **When unsure** — search the web for current Salesforce documentation to confirm syntax
4. **Test mentally** — walk through the generated code checking for:
   - Correct field references (labels vs API names vs dot notation)
   - Correct string quoting (single vs double)
   - GROUP BY using aliases (for CIs)
   - Explicit AS aliases (for streaming transforms)
   - No unsupported functions (LEFT in transforms, IN with functions in transforms)
   - No comments (in streaming transforms)
5. **Never guess** — if a syntax pattern hasn't been validated, search for it first

## Additional syntax reference

For full function reference and advanced examples, see [dc-syntax-reference.md](dc-syntax-reference.md).
