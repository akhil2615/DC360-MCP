# Data Cloud Syntax Reference

Full function and operator reference for Data Cloud (Data 360) formula fields and SQL.

## CRITICAL RULES for formula fields

```
1. sourceField uses LABELS (display names), NOT API names:
   CORRECT:  sourceField['Email']
   WRONG:    sourceField['Email__c']

2. AND / OR are INFIX OPERATORS, NOT functions:
   CORRECT:  (sourceField['Country'] == "US") OR (sourceField['Country'] == "USA")
   WRONG:    OR(sourceField['Country'] == "US", sourceField['Country'] == "USA")

3. String values use DOUBLE QUOTES, field labels use single quotes:
   CORRECT:  sourceField['Email'] == "test@test.com"
   WRONG:    sourceField['Email'] == 'test@test.com'
```

---

## Formula Fields — Supported Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `==` | Equal | `sourceField['Status'] == "Active"` |
| `!=` | Not equal | `sourceField['Country'] != "US"` |
| `>` | Greater than | `sourceField['Age'] > 18` |
| `<` | Less than | `sourceField['Score'] < 100` |
| `>=` | Greater than or equal | `sourceField['Amount'] >= 50` |
| `<=` | Less than or equal | `sourceField['Amount'] <= 1000` |
| `AND` | Logical AND (infix) | `(condition1) AND (condition2)` |
| `OR` | Logical OR (infix) | `(condition1) OR (condition2)` |
| `NOT` | Logical NOT (prefix) | `NOT (condition)` |

---

## Formula Fields — Supported Functions

### Conditional

| Function | Signature | Notes |
|----------|-----------|-------|
| `IF` | `IF(condition, trueVal, falseVal)` | Nestable for multi-branch logic |

### String

| Function | Signature | Notes |
|----------|-----------|-------|
| `LEFT` | `LEFT(text, n)` | First n characters |
| `RIGHT` | `RIGHT(text, n)` | Last n characters |
| `MID` | `MID(text, start, length)` | Substring; 1-indexed |
| `SUBSTITUTE` | `SUBSTITUTE(text, old, new)` | Replace all occurrences |
| `TRIM` | `TRIM(text)` | Remove leading/trailing whitespace |
| `UPPER` | `UPPER(text)` | Uppercase |
| `LOWER` | `LOWER(text)` | Lowercase |
| `LEN` | `LEN(text)` | Character count |
| `EXTRACT` | `EXTRACT(text, pattern)` | Regex extract (first match) |
| `PROPER` | `PROPER(text)` | Title Case conversion |

### Type Conversion

| Function | Signature | Notes |
|----------|-----------|-------|
| `NUMBER` | `NUMBER(text)` | Parse string to number |
| `TEXT` | `TEXT(value)` | Convert to string |
| `ABS` | `ABS(number)` | Absolute value |
| `MD5` | `MD5(text)` | Returns hex MD5 hash |

### Date / Time

| Function | Signature | Notes |
|----------|-----------|-------|
| `PARSEDATE` | `PARSEDATE(text, 'format')` | e.g. `PARSEDATE(sourceField['DateField'], 'yyyy-MM-dd')` |
| `DATE` | `DATE(year, month, day)` | Construct a date literal |
| `DATEDIFF` | `DATEDIFF('unit', start, end)` | Units: DAY, MONTH, YEAR |
| `DAYPRECISION` | `DAYPRECISION(dateTimeField)` | Truncate timestamp to date |
| `NOW()` | `NOW()` | Current datetime in UTC |
| `TODAY()` | `TODAY()` | Current date (no time) |

**Common PARSEDATE format strings:**

| Format | Example input |
|--------|---------------|
| `yyyy-MM-dd` | `2024-01-15` |
| `MM/dd/yyyy` | `01/15/2024` |
| `dd-MMM-yyyy` | `15-Jan-2024` |
| `yyyyMMdd` | `20240115` |
| `yyyy-MM-dd'T'HH:mm:ss` | `2024-01-15T09:30:00` |

---

## Formula Field Considerations

- Formula fields are **only evaluated at data ingestion time**
- To recalculate, you must perform a **Full Refresh** of the Data Stream
- Formula fields do **not consume extra credits** beyond ingestion charges
- Data transforms are more flexible but consume additional credits
- Formula fields output types: Text, Number, Date, Boolean

---

## Formula Patterns (official syntax)

**String to boolean (Y/N):**
```
IF(sourceField['Status'] == "Y", true, IF(sourceField['Status'] == "N", false, null))
```

**Replace placeholder with null:**
```
IF(sourceField['Name'] != "Anonymous", sourceField['Name'], null)
```

**Multi-branch mapping:**
```
IF(sourceField['Code'] == "ADV", "Advertisement",
  IF(sourceField['Code'] == "INS", "In-Store",
    IF(sourceField['Code'] == "AFF", "Affiliate", "Other")))
```

**Combining conditions with AND (infix):**
```
(sourceField['MailingCountry'] != "USA") AND (sourceField['MailingCountry'] != "US")
```

**Combining conditions with OR (infix):**
```
(sourceField['Email'] == "test@test.com") OR (sourceField['Email'] == "na@na.com")
```

**Title Case:**
```
PROPER(sourceField['FirstName'])
```

**Generate timestamp for engagement streams:**
```
NOW()
```

**Date from string:**
```
PARSEDATE(sourceField['DateString'], 'yyyy-MM-dd')
```

**Date from parts:**
```
DATE(NUMBER(LEFT(sourceField['yyyymmdd'], 4)),
     NUMBER(MID(sourceField['yyyymmdd'], 5, 2)),
     NUMBER(RIGHT(sourceField['yyyymmdd'], 2)))
```

---

## Query Editor SQL — Validated Syntax and Patterns

Query Editor SQL uses standard PostgreSQL dialect with DMO API names directly
(no dot notation — that's streaming transforms only).

### Key syntax rules for Query Editor

```
1. Table names are DMO/DLO API names used directly: ssot__Individual__dlm
2. Field names include the full prefix: ssot__FirstName__c, ssot__Id__c
3. No double-quoting required (same as Calculated Insights and Streaming Transforms)
4. Table aliases are supported: FROM ssot__Individual__dlm a
5. Fields reference via alias: a.ssot__FirstName__c
6. String literals use SINGLE QUOTES: 'value'
7. JOIN syntax: JOIN table ON condition
8. Subqueries in WHERE are supported
9. Window functions: ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...)
10. Date arithmetic: column + interval '9 hour'
11. LIMIT recommended: always add LIMIT 10000 max (>10K may crash UI)
12. Query timeout: 5 minutes max
13. Comments ARE allowed in Query Editor (-- style) unlike streaming transforms
```

### Check Email Engagement (multi-JOIN pattern)

```sql
SELECT
    a.ssot__IndividualId__c AS Id,
    a.ssot__SendtimeEmailAddress__c AS Email,
    i.ssot__FirstName__c AS FirstName,
    i.ssot__LastName__c AS LastName,
    a.ssot__EngagementDateTm__c AS EngagementDateTime,
    a.ssot__EngagementChannelActionId__c AS ActionName,
    a.ssot__EmailRecipientSendStatus__c AS SendStatus,
    c.ssot__Name__c AS EmailElementAPIName,
    e.ssot__Name__c AS FlowName,
    a.ssot__BounceReasonText__c AS BounceReason
FROM ssot__EmailEngagement__dlm a
JOIN ssot__FlowElementRun__dlm b ON a.ssot__FlowElementRunId__c = b.ssot__Id__c
JOIN ssot__FlowElement__dlm c ON b.ssot__FlowElementId__c = c.ssot__Id__c
JOIN ssot__FlowVersion__dlm d ON c.ssot__FlowVersionId__c = d.ssot__Id__c
JOIN ssot__Flow__dlm e ON d.ssot__FlowId__c = e.ssot__Id__c
JOIN ssot__BulkEmailMessage__dlm g ON a.ssot__BulkEmailMessageId__c = g.ssot__Id__c
LEFT OUTER JOIN ssot__MarketSegment__dlm h ON g.ssot__MarketSegmentId__c = h.ssot__Id__c
JOIN ssot__Individual__dlm i ON a.ssot__IndividualId__c = i.ssot__Id__c
ORDER BY a.ssot__EngagementDateTm__c DESC
LIMIT 10
```

### Check Website Engagement

```sql
SELECT
    ssot__IndividualId__c AS Id,
    ssot__EngagementDateTm__c AS EngagementDateTime,
    ssot__PagePublicTitleName__c AS PageTitle,
    ssot__EngagementChannelActionId__c AS ActionName,
    ssot__LinkURL__c AS ClickLinkURL,
    ssot__ReferrerURL__c AS ReferrerURL,
    ssot__OSName__c AS OSName,
    ssot__BrowserName__c AS BrowserName
FROM ssot__WebsiteEngagement__dlm
ORDER BY ssot__EngagementDateTm__c DESC
LIMIT 10
```

### Look up Unified Record from Individual ID (Identity Resolution)

```sql
SELECT UnifiedId, Id, FirstName, LastName, Email, DataSource
FROM (
    SELECT
        b.UnifiedRecordId__c AS UnifiedId,
        b.SourceRecordId__c AS Id,
        d.ssot__FirstName__c AS FirstName,
        d.ssot__LastName__c AS LastName,
        c.ssot__EmailAddress__c AS Email,
        b.ssot__DataSourceObjectId__c AS DataSource,
        ROW_NUMBER() OVER (
            PARTITION BY b.SourceRecordId__c, c.ssot__EmailAddress__c
            ORDER BY c.ssot__LastModifiedDate__c DESC
        ) AS rn
    FROM IndividualIdentityLink__dlm a
    LEFT OUTER JOIN IndividualIdentityLink__dlm b
        ON a.UnifiedRecordId__c = b.UnifiedRecordId__c
    LEFT OUTER JOIN ssot__ContactPointEmail__dlm c
        ON b.SourceRecordId__c = c.ssot__PartyId__c
    LEFT OUTER JOIN UnifiedIndividual__dlm d
        ON a.UnifiedRecordId__c = d.ssot__Id__c
    WHERE a.SourceRecordId__c = '***'
) t
WHERE rn = 1
ORDER BY Id
LIMIT 10
```

### Check Consent Status from Email

```sql
SELECT ContactPointValue, Status, SubscriptionName, ChannelName, LastModifiedDate
FROM (
    SELECT
        a.ssot__ContactPointValueText__c AS ContactPointValue,
        a.ssot__ConsentStatus__c AS Status,
        c.ssot__Name__c AS SubscriptionName,
        d.ssot__Name__c AS ChannelName,
        a.ssot__LastModifiedDate__c AS LastModifiedDate,
        ROW_NUMBER() OVER (
            PARTITION BY a.ssot__ContactPointValueText__c, c.ssot__Name__c
            ORDER BY a.ssot__LastModifiedDate__c DESC
        ) AS rn
    FROM ssot__CommunicationSubscriptionConsent__dlm a
    JOIN ssot__CommunicationSubscriptionChannelType__dlm b
        ON a.ssot__CommunicationSubscriptionChannelTypeId__c = b.ssot__Id__c
    JOIN ssot__CommunicationSubscription__dlm c
        ON b.ssot__CommunicationSubscriptionId__c = c.ssot__Id__c
    JOIN ssot__EngagementChannelType__dlm d
        ON b.ssot__EngagementChannelTypeId__c = d.ssot__Id__c
) sub
WHERE rn = 1
ORDER BY LastModifiedDate DESC
```

### Check Identity Match Status

```sql
SELECT
    ssot__DataSourceObjectId__c AS DataSourceName,
    ssot__RecordId__c AS RecordId,
    ssot__MatchingRecordId__c AS MatchingRecordId,
    ssot__IdentityMatchType__c AS IdentityMatchType,
    ssot__CreatedDate__c AS CreatedDate,
    ssot__IdentityMatchWeight__c AS IdentityMatchWeight,
    ssot__IsAMatch__c AS IdentityMatchFlag
FROM ssot__IdentityMatch__dlm
ORDER BY ssot__IdentityMatchWeight__c DESC, ssot__CreatedDate__c DESC
LIMIT 10
```

### Check Ingestion Status into Individual DMO

```sql
SELECT
    a.ssot__Id__c AS Id,
    a.ssot__FirstName__c AS FirstName,
    a.ssot__LastName__c AS LastName,
    b.ssot__EmailAddress__c AS Email,
    a.ssot__DataSourceObjectId__c AS DataSource,
    a.ssot__LastModifiedDate__c AS LastModifiedDate,
    a.ssot__CreatedDate__c AS CreatedDate
FROM ssot__Individual__dlm a
LEFT JOIN (
    SELECT ssot__PartyId__c,
           ssot__EmailAddress__c,
           ROW_NUMBER() OVER (PARTITION BY ssot__PartyId__c ORDER BY ssot__LastModifiedDate__c DESC) AS rn
    FROM ssot__ContactPointEmail__dlm
) b ON a.ssot__Id__c = b.ssot__PartyId__c AND b.rn = 1
ORDER BY a.ssot__LastModifiedDate__c DESC
LIMIT 10
```

### Key DMO join paths (common relationships)

```
Individual → Contact Point Email:   ssot__Individual__dlm.ssot__Id__c = ssot__ContactPointEmail__dlm.ssot__PartyId__c
Individual → Contact Point Phone:   ssot__Individual__dlm.ssot__Id__c = ssot__ContactPointPhone__dlm.ssot__PartyId__c
Individual → Contact Point Address: ssot__Individual__dlm.ssot__Id__c = ssot__ContactPointAddress__dlm.ssot__PartyId__c
Individual → Unified Link:          IndividualIdentityLink__dlm.SourceRecordId__c = ssot__Individual__dlm.ssot__Id__c
Unified Link → Unified Individual:  IndividualIdentityLink__dlm.UnifiedRecordId__c = UnifiedIndividual__dlm.ssot__Id__c
Email Engagement → Flow Element Run: ssot__EmailEngagement__dlm.ssot__FlowElementRunId__c = ssot__FlowElementRun__dlm.ssot__Id__c
Flow Element Run → Flow Element:    ssot__FlowElementRun__dlm.ssot__FlowElementId__c = ssot__FlowElement__dlm.ssot__Id__c
Flow Element → Flow Version:        ssot__FlowElement__dlm.ssot__FlowVersionId__c = ssot__FlowVersion__dlm.ssot__Id__c
Flow Version → Flow:                ssot__FlowVersion__dlm.ssot__FlowId__c = ssot__Flow__dlm.ssot__Id__c
Email Engagement → Bulk Email Msg:  ssot__EmailEngagement__dlm.ssot__BulkEmailMessageId__c = ssot__BulkEmailMessage__dlm.ssot__Id__c
Bulk Email Msg → Market Segment:    ssot__BulkEmailMessage__dlm.ssot__MarketSegmentId__c = ssot__MarketSegment__dlm.ssot__Id__c
```

---

## Calculated Insights SQL — Syntax and Patterns

### CI SQL syntax rules

```
1. Table/field names used DIRECTLY — NO double-quoting needed
2. Table aliases supported: FROM ssot__SalesOrder__dlm S
3. All measure/dimension aliases MUST end with __c suffix:
   CORRECT:  SUM(amount) AS total_spend__c
   WRONG:    SUM(amount) AS TotalSpend
4. Every SELECT must have at least one MEASURE (aggregate) and one DIMENSION
5. GROUP BY uses the ALIAS name: GROUP BY CustomerId__c
6. String literals use SINGLE QUOTES: 'value'
7. Standard join path to unified profiles:
   DMO → IndividualIdentityLink__dlm (SourceRecordId__c) → UnifiedIndividual__dlm (ssot__Id__c)
```

### Types of Insights

| Type | Description | When to use |
|------|-------------|-------------|
| Visual Builder | Low-code drag-and-drop | Non-technical users, simple aggregations |
| SQL Editor | Full SQL control | Complex joins, CASE logic, window functions |
| Streaming Insights | Real-time 5-min windows | Live fraud detection, real-time scoring |
| Data-Kits | Pre-built packages | Quick start with standard metrics |

### Visual Builder workflow

1. Select primary object (e.g. Reservation DMO)
2. Click (+) → Join → select related object (e.g. Unified Individual)
3. Data Cloud auto-creates join path through Individual → Unified Link → Unified Individual
4. Click (+) → Aggregate → select field (e.g. Reservation Id)
5. Under Measures: click (+) → select function (Count, Sum, Avg, Min, Max)
6. Set Metric Name (e.g. "Lifetime Total Reservations")
7. Under Dimensions: click (+) → select grouping field (e.g. Unified Individual Id)
8. Click Publish Now → Save and Run

### Spend by Customer (beginner)

```sql
SELECT
    SUM(ssot__SalesOrder__dlm.ssot__GrandTotalAmount__c) AS customer_spend__c,
    UnifiedIndividual__dlm.ssot__Id__c AS CustomerId__c
FROM ssot__SalesOrder__dlm
LEFT JOIN IndividualIdentityLink__dlm
    ON ssot__SalesOrder__dlm.ssot__SoldToCustomerId__c = IndividualIdentityLink__dlm.SourceRecordId__c
LEFT JOIN UnifiedIndividual__dlm
    ON IndividualIdentityLink__dlm.UnifiedRecordId__c = UnifiedIndividual__dlm.ssot__Id__c
GROUP BY CustomerId__c
```
| Measure | Dimension |
|---------|-----------|
| customer_spend__c | CustomerId__c |

### Lifetime Value (LTV) with product dimensions

```sql
SELECT
    SUM(ssot__SalesOrder__dlm.ssot__GrandTotalAmount__c) AS LTV__c,
    UnifiedIndividual__dlm.ssot__Id__c AS CustomerId__c,
    CDPHour(ssot__SalesOrder__dlm.ssot__PurchaseOrderDate__c) AS PurchaseHour__c,
    ssot__GoodsProduct__dlm.Category__c AS ProductCategory__c,
    ssot__SalesOrder__dlm.ssot__SalesChannelId__c AS SalesChannel__c
FROM ssot__SalesOrder__dlm
LEFT JOIN IndividualIdentityLink__dlm
    ON ssot__SalesOrder__dlm.ssot__SoldToCustomerId__c = IndividualIdentityLink__dlm.SourceRecordId__c
LEFT JOIN UnifiedIndividual__dlm
    ON IndividualIdentityLink__dlm.UnifiedRecordId__c = UnifiedIndividual__dlm.ssot__Id__c
LEFT JOIN ssot__SalesOrderProduct__dlm
    ON ssot__SalesOrderProduct__dlm.ssot__SalesOrderId__c = ssot__SalesOrder__dlm.ssot__OrderNumber__c
LEFT JOIN ssot__GoodsProduct__dlm
    ON ssot__SalesOrderProduct__dlm.ssot__ProductId__c = ssot__GoodsProduct__dlm.ssot__ProductSKU__c
GROUP BY CustomerId__c, PurchaseHour__c, ProductCategory__c, SalesChannel__c
```

### Customer Rank by Spend (window functions)

```sql
SELECT
    UnifiedIndividual__dlm.ssot__Id__c AS Unified_Individual__c,
    ROW_NUMBER() OVER (ORDER BY SUM(ssot__SalesOrder__dlm.ssot__GrandTotalAmount__c) DESC) AS Customer_Rank__c,
    DENSE_RANK() OVER (ORDER BY SUM(ssot__SalesOrder__dlm.ssot__GrandTotalAmount__c) DESC) AS Customer_Dense_Rank__c,
    RANK() OVER (ORDER BY SUM(ssot__SalesOrder__dlm.ssot__GrandTotalAmount__c) DESC) AS Customer_Stat_Rank__c
FROM UnifiedIndividual__dlm
INNER JOIN IndividualIdentityLink__dlm
    ON UnifiedIndividual__dlm.ssot__Id__c = IndividualIdentityLink__dlm.UnifiedRecordId__c
INNER JOIN ssot__SalesOrder__dlm
    ON IndividualIdentityLink__dlm.SourceRecordId__c = ssot__SalesOrder__dlm.ssot__SoldToCustomerId__c
GROUP BY Unified_Individual__c
```

### RFM Scoring with NTILE and subquery

```sql
SELECT
    sub.cust_id__c AS id__c,
    First(sub.rfm_recency__c * 100 + sub.rfm_frequency__c * 10 + sub.rfm_monetary__c) AS rfm_combined__c,
    First(sub.rfm_recency__c) AS Recency__c,
    First(sub.rfm_frequency__c) AS Frequency__c,
    First(sub.rfm_monetary__c) AS Monetary__c
FROM (
    SELECT
        UnifiedIndividual__dlm.ssot__Id__c AS cust_id__c,
        NTILE(4) OVER (ORDER BY MAX(ssot__SalesOrder__dlm.ssot__PurchaseOrderDate__c)) AS rfm_recency__c,
        NTILE(4) OVER (ORDER BY COUNT(ssot__SalesOrder__dlm.ssot__Id__c)) AS rfm_frequency__c,
        NTILE(4) OVER (ORDER BY AVG(ssot__SalesOrder__dlm.ssot__GrandTotalAmount__c)) AS rfm_monetary__c
    FROM ssot__SalesOrder__dlm
    LEFT JOIN IndividualIdentityLink__dlm
        ON ssot__SalesOrder__dlm.ssot__SoldToCustomerId__c = IndividualIdentityLink__dlm.SourceRecordId__c
    LEFT JOIN UnifiedIndividual__dlm
        ON UnifiedIndividual__dlm.ssot__Id__c = IndividualIdentityLink__dlm.UnifiedRecordId__c
    GROUP BY UnifiedIndividual__dlm.ssot__Id__c
) AS sub
GROUP BY sub.cust_id__c
```

### CASE bucketing (driver safety example pattern)

```sql
SELECT
    CASE
        WHEN SUM(engagement_count__c) > 20 THEN 'High'
        WHEN SUM(engagement_count__c) > 10 THEN 'Medium'
        WHEN SUM(engagement_count__c) > 0 THEN 'Low'
        ELSE 'None'
    END AS engagement_bucket__c,
    customer_id__c AS id__c
FROM (
    SELECT
        COUNT(ssot__EmailEngagement__dlm.ssot__Id__c) AS engagement_count__c,
        UnifiedIndividual__dlm.ssot__Id__c AS customer_id__c
    FROM ssot__EmailEngagement__dlm
    JOIN IndividualIdentityLink__dlm
        ON ssot__EmailEngagement__dlm.ssot__IndividualId__c = IndividualIdentityLink__dlm.SourceRecordId__c
    JOIN UnifiedIndividual__dlm
        ON IndividualIdentityLink__dlm.UnifiedRecordId__c = UnifiedIndividual__dlm.ssot__Id__c
    GROUP BY UnifiedIndividual__dlm.ssot__Id__c
) AS S
GROUP BY id__c
```

### Email Open Count per Unified Individual

```sql
SELECT
    COUNT(ssot__EmailEngagement__dlm.ssot__Id__c) AS email_open_count__c,
    UnifiedIndividual__dlm.ssot__Id__c AS customer_id__c
FROM ssot__EmailEngagement__dlm
JOIN IndividualIdentityLink__dlm
    ON IndividualIdentityLink__dlm.SourceRecordId__c = ssot__EmailEngagement__dlm.ssot__IndividualId__c
    AND ssot__EmailEngagement__dlm.ssot__EngagementChannelActionId__c = 'Open'
JOIN UnifiedIndividual__dlm
    ON UnifiedIndividual__dlm.ssot__Id__c = IndividualIdentityLink__dlm.UnifiedRecordId__c
GROUP BY customer_id__c
```

### NOT IN with WHERE subquery

```sql
SELECT
    AVG(ssot__SalesOrder__dlm.ssot__GrandTotalAmount__c) AS avg__c,
    ssot__SalesOrder__dlm.ssot__SoldToCustomerId__c AS customer_id__c
FROM ssot__SalesOrder__dlm
WHERE ssot__SalesOrder__dlm.ssot__SoldToCustomerId__c NOT IN (
    SELECT ssot__Individual__dlm.ssot__Id__c
    FROM ssot__Individual__dlm
    WHERE ssot__Individual__dlm.Loyalty_Reward_Points__c > 10
)
GROUP BY customer_id__c
```

### CI Supported functions reference

| Category | Functions |
|----------|-----------|
| Aggregate | `SUM()`, `COUNT()`, `AVG()`, `MIN()`, `MAX()`, `FIRST()` |
| Window | `ROW_NUMBER()`, `RANK()`, `DENSE_RANK()`, `NTILE()` with `OVER (ORDER BY ...)` |
| Conditional | `CASE WHEN ... THEN ... ELSE ... END` |
| Date | `CDPHour()` for time-period dimensions |
| Subquery | `NOT IN (subquery)`, inline views `FROM (SELECT ...) AS alias` |
| String | Standard string functions |
| Comparison | `=`, `<>`, `<`, `>`, `<=`, `>=`, `AND`, `OR`, `NOT` |
| JOINs | `INNER JOIN`, `LEFT JOIN`, `LEFT OUTER JOIN` with `ON` |

### CI NOT SUPPORTED (will cause syntax errors)

| Feature | Alternative |
|---------|-------------|
| `CURRENT_DATE` | Use CI Lookback Period setting in the UI |
| `INTERVAL '90 days'` | Use CI Lookback Period setting in the UI |
| Date arithmetic in WHERE | Configure lookback when creating the CI |
| Non-aggregate filters in WHERE (e.g. `name IS NOT NULL`) | Apply these in the Segment on top of the CI |
| GROUP BY with field references | GROUP BY MUST use alias names |

### CI GROUP BY rules

```
CORRECT:
  SELECT COUNT(x) AS count__c, Table.Field AS dimension__c
  FROM ...
  GROUP BY dimension__c

WRONG:
  SELECT COUNT(x) AS count__c, Table.Field AS dimension__c
  FROM ...
  GROUP BY Table.Field
```

Put measures (aggregates) BEFORE dimensions in the SELECT list.

---

## Segment Builder — Complete Reference

### Segment types

| Type | Description | Use case |
|------|-------------|----------|
| Standard | Static criteria, scheduled refresh | Recurring campaigns, broad audiences |
| Rapid Publish | Near-instant output | Marketing Cloud real-time activation |
| Waterfall | Hierarchical priority ordering | Prevent customers receiving multiple offers |
| Nested | Include/exclude one segment from another | Refine existing segments |
| Real-time | Dynamic, updates as data flows in | Live personalization, triggered experiences |
| Einstein Lookalike | AI-driven similar audience discovery | Find prospects similar to best customers |

### Segment On entity selection

- Use `UnifiedIndividual__dlm` (not `ssot__Individual__dlm`) when data comes from multiple sources
- Unified objects have fewer records (deduplicated) = better performance
- For B2B: use `UnifiedAccount__dlm`

### Attribute types

| Type | Relationship | Example | Container needed? |
|------|-------------|---------|-------------------|
| Direct | 1:1 or N:1 with Segment On | FirstName, Country | No |
| Related | 1:N with Segment On | Purchases, Email engagements | Yes (Container) |
| Calculated Insight | Pre-computed metric | LTV, RFM Score | No (acts as direct) |

### Operator reference by data type

**Text operators:**
| Operator | Description |
|----------|-------------|
| Is Equal To | Exact match |
| Is Not Equal To | Exact non-match |
| Contains | Substring match |
| Does Not Contain | Substring exclusion |
| Begins With | Prefix match |
| Exists As A Whole Word | Word boundary match |
| Is In | Multiple value match (comma-separated) |
| Is Not In | Multiple value exclusion |

**Number operators:**
| Operator | Description |
|----------|-------------|
| Is Equal To / Is Not Equal To | Exact numeric match |
| Is Less Than / Is Less Than Or Equal To | Lower bound |
| Is Greater Than / Is Greater Than Or Equal To | Upper bound |
| Is Between / Is Not Between | Range (inclusive) |
| No Value | Null check |

**Date operators:**
| Operator | Description |
|----------|-------------|
| Is On | Exact date |
| Is Before / Is After | Boundary (exclusive) |
| Is Between | Date range |
| Last N Days / Next N Days | Rolling day window |
| Last N Months / Next N Months | Rolling month window |
| Is Anniversary Of / Is Not Anniversary Of | Annual recurrence |
| Day Of Week / Day Of Month / Not Day Of Month | Specific day pattern |
| This Year / Last Year / Next Year | Year-based |

**Boolean operators:**
| Operator | Description |
|----------|-------------|
| Is True / Is Not True | True check |
| Is False / Is Not False | False check |
| Is Unknown / Is Not Unknown | Null check |

### Container concepts

Containers wrap **Related Attributes** (1:N relationships). Each container has:
- **Container Path** — the join path from Segment On to the related DMO
- **Aggregation** — Count, Sum, Average, Min, Max on the related records
- **Filters** — conditions applied to the related records inside the container
- **Logic** — AND/OR combining filters within the container

### Aggregation types with examples

| Aggregation | Use case example |
|-------------|-----------------|
| Count | "At least 5 purchases" — Count of SalesOrder >= 5 |
| Sum | "Lifetime spend of $1500" — Sum of GrandTotalAmount >= 1500 |
| Average | "Avg order value > $200" — Avg of GrandTotalAmount > 200 |
| Max | "Largest order < $1000" — Max of GrandTotalAmount < 1000 |
| Min | "Smallest order > $5" — Min of GrandTotalAmount > 5 |

### Container path rules

- Always choose the **shortest path** between Segment On and the related DMO
- **Avoid cyclic paths** (a→b→c→a or a→b→c→b) — they cause timeouts
- Once saved, container paths cannot be changed — delete and recreate if wrong
- Only one container path per attribute

### Example segment — High-value recent purchasers in US

```
Segment On: UnifiedIndividual__dlm
Type: Standard

Direct Attributes:
  Group 1 (AND):
    - Field: ssot__CountryId__c (from Contact Point Address via shortest path)
      Operator: Is Equal To
      Value: US

Container 1 (Related: ssot__SalesOrder__dlm):
  Path: UnifiedIndividual__dlm → IndividualIdentityLink__dlm → ssot__SalesOrder__dlm
  Aggregation: Sum of ssot__GrandTotalAmount__c
  Operator: Is Greater Than Or Equal To
  Value: 500
  Filters (AND):
    - Field: ssot__PurchaseOrderDate__c
      Operator: Last 90 Days

Container 2 (Related: ssot__ContactPointEmail__dlm):
  Path: UnifiedIndividual__dlm → IndividualIdentityLink__dlm → ssot__Individual__dlm → ssot__ContactPointEmail__dlm
  Aggregation: Count
  Operator: Is Greater Than Or Equal To
  Value: 1
  Filters:
    - Field: ssot__EmailAddress__c
      Operator: Does Not Contain
      Value: noemail

Logic: Direct AND Container 1 AND Container 2
```

### Example — Email engagement bucket using CI

```
Segment On: UnifiedIndividual__dlm
Type: Standard

Calculated Insight Attribute:
  Insight: EmailEngagementBuckets (CI)
  Measure: engagement_bucket__c
  Operator: Is Equal To
  Value: High

Direct Attributes:
  - Field: ssot__IsAnonymous__c (from Individual)
    Operator: Is Not Equal To
    Value: 1
```

### Example — Waterfall segment (mutually exclusive offers)

```
Waterfall Segment: Holiday Campaign Offers
Priority Order (drag-and-drop):
  1. VIP_Customers_Segment (gets 30% offer)
  2. Frequent_Buyers_Segment (gets 20% offer)
  3. New_Customers_Segment (gets 10% welcome offer)
  4. All_Other_Customers_Segment (gets general newsletter)

Each customer only appears in the highest-priority segment they qualify for.
```

### Best practices

1. **Segment On**: Use Unified objects over raw DMOs for deduplication
2. **Merge containers**: Same-path containers joined by OR → merge into one container
3. **Nested operators**: Use AND/OR nesting (up to 5 levels) inside one container
4. **Nested segments**: Use membership mode over definition mode for performance
5. **Engagement filters**: Add explicit Event Date Time filter to reduce data scanned
6. **Use CIs**: Pre-compute heavy metrics (LTV, RFM) in Calculated Insights
7. **Correct DMO types**: Map engagement data to Engagement-type DMOs for partitioning
8. **Data Spaces**: Use Data Spaces to logically partition and reduce data volume
9. **Avoid cyclic paths**: Check for a→b→c→a patterns — use direct attributes instead
10. **Skewed data**: Avoid using engagement data with uneven date distribution

---

## Streaming Transform — Syntax and Patterns

**Streaming transforms use completely different syntax from formula fields.**
They are SQL queries with `DLOName.FieldName` dot notation.

### Critical syntax rules

```
1. DOT NOTATION with FULL DLO name (including __dll suffix):
   CORRECT:  Lead_Home__dll.Email__c
   WRONG:    Lead_Home.Email__c      ← missing __dll suffix
   WRONG:    sourceField['Email']    ← that's formula field syntax
   WRONG:    Email__c                ← bare name without DLO prefix

2. EVERY field MUST have an explicit AS alias:
   CORRECT:  Lead_Home__dll.Email__c AS Email__c
   WRONG:    Lead_Home__dll.Email__c         ← no alias, causes NULL alias error

3. FROM clause uses FULL DLO name:
   FROM Lead_Home__dll

4. String literals use SINGLE QUOTES (double quotes are for identifiers only):
   CORRECT:  'Mobile'    IN ('US', 'USA')
   WRONG:    "Mobile"    IN ("US", "USA")

5. Null checks:
   ISNOTNULL(DLO.Field)   — check for non-null
   ISNULL(DLO.Field)      — check for null

6. Not-equal operator:
   DLO.Field <> ''        — not-equal

7. NEVER add SQL comments (-- or /* */):
   They cause syntax errors in the streaming transform engine

8. NOT SUPPORTED functions:
   LEFT(), RIGHT(), MID(), FIND()
   Use SUBSTRING(text, start, length) instead of LEFT(text, n)
```

### Normalize phone contacts (official Salesforce example, adapted for single quotes)

```sql
SELECT
    CONCAT(Contact_core__dll.CustomerId, '_Mobile') AS PhoneId,
    Contact_core__dll.CustomerId AS CustomerId,
    Contact_core__dll.MobilePhone AS PhoneNumber,
    'Mobile' AS PhoneType
FROM Contact_core__dll
WHERE ISNOTNULL(Contact_core__dll.MobilePhone) AND Contact_core__dll.MobilePhone <> ''
UNION
SELECT
    CONCAT(Contact_core__dll.CustomerId, '_Home') AS PhoneId,
    Contact_core__dll.CustomerId AS CustomerId,
    Contact_core__dll.HomePhone AS PhoneNumber,
    'Home' AS PhoneType
FROM Contact_core__dll
WHERE ISNOTNULL(Contact_core__dll.HomePhone) AND Contact_core__dll.HomePhone <> ''
```

### Conditional mapping (chained OR instead of IN with UPPER)

```sql
SELECT
    Lead_Home__dll.Id__c AS Id__c,
    CASE
        WHEN UPPER(TRIM(Lead_Home__dll.Country__c)) = 'US'
            OR UPPER(TRIM(Lead_Home__dll.Country__c)) = 'USA'
            OR UPPER(TRIM(Lead_Home__dll.Country__c)) = 'UNITED STATES'
            THEN 'United States'
        WHEN UPPER(TRIM(Lead_Home__dll.Country__c)) = 'GB'
            OR UPPER(TRIM(Lead_Home__dll.Country__c)) = 'UK'
            OR UPPER(TRIM(Lead_Home__dll.Country__c)) = 'UNITED KINGDOM'
            THEN 'United Kingdom'
        ELSE Lead_Home__dll.Country__c
    END AS Country_Normalized__c
FROM Lead_Home__dll
```

### Type coercions

```sql
CAST(Lead_Home__dll.AnnualRevenue__c AS BIGINT)
CAST(Lead_Home__dll.IsConverted__c AS BOOLEAN)
```

### Supported functions

| Category | Functions |
|----------|-----------|
| String | `CONCAT()`, `LOWER()`, `UPPER()`, `TRIM()`, `LENGTH()`, `SUBSTRING()`, `REPLACE()`, `REGEXP_REPLACE()` |
| Conditional | `CASE WHEN … THEN … ELSE … END`, `COALESCE()`, `ISNULL()`, `ISNOTNULL()` |
| Type | `CAST(expr AS type)`, `TO_DATE()`, `TO_TIMESTAMP()` |
| Date | `NOW()`, `TODAY()` |
| Set ops | `UNION`, `UNION ALL` |
| Logical | `AND`, `OR`, `NOT` (infix) |
| Comparison | `=`, `<>`, `<`, `>`, `<=`, `>=`, `IN (…)`, `NOT IN (…)` |
| JOINs | `INNER JOIN`, `LEFT JOIN`, `RIGHT JOIN`, `FULL OUTER JOIN` with `ON` |

---

## Data Cloud Key Concepts Cheat Sheet

| Term | Meaning |
|------|---------|
| DLO | Data Lake Object — raw ingested table (suffix `__dll`) |
| DMO | Data Model Object — harmonised canonical table (suffix `__dlm`) |
| Data Stream | Pipeline that ingests data and maps DLO → DMO |
| Formula Field | Derived field computed at ingestion time from DLO fields |
| Streaming Transform | SQL-like transform applied mid-stream before DMO mapping |
| Identity Resolution | Ruleset that stitches records into a Unified Individual |
| Unified Individual | `UnifiedIndividual__dlm` — the golden record for a person |
| Calculated Insight | SQL-defined metric stored as a DMO (suffix `__insight`) |
| Segment | Audience filter built on DMOs and Calculated Insights |
| Activation | Publishing a segment to an external system |
| Data Graph | JSON bundle of related DMO data for a single profile |
| Dataspace | Isolated partition within a Data Cloud org |
| Query API | REST endpoint for running SQL against Data Cloud |
