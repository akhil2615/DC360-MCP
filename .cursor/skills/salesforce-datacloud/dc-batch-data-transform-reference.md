# Batch Data Transform JSON Reference

Comprehensive reference for generating valid JSON definitions for Salesforce Data Cloud
**Batch Data Transforms** (BDT). The JSON produced by this skill is intended to be
imported via the BDT canvas (Data Cloud → Data Transforms → New → Import) so users can
generate complete pipelines from a natural-language requirement.

## Sources of truth (Salesforce help docs)

- Overview: https://help.salesforce.com/s/articleView?id=data.c360_a_batch_transform_overview.htm
- Working with nodes: https://help.salesforce.com/s/articleView?id=data.c360_a_batch_transform_nodes_overview.htm
- Input / Output nodes: https://help.salesforce.com/s/articleView?id=data.c360_a_batch_transform_input_and_output_nodes.htm
- Append node: https://help.salesforce.com/s/articleView?id=data.c360_a_batch_transform_append_node.htm
- Aggregate node: https://help.salesforce.com/s/articleView?id=data.c360_a_batch_transform_aggregate.htm
- Filter node: https://help.salesforce.com/s/articleView?id=data.c360_a_batch_transform_filter.htm
- Join overview: https://help.salesforce.com/s/articleView?id=data.c360_a_batch_transform_join.htm
- Join operations: https://help.salesforce.com/s/articleView?id=data.c360_a_batch_transform_join_operations.htm
- Transform node: https://help.salesforce.com/s/articleView?id=data.c360_a_batch_transform_transform_node.htm
- Transformations catalog: https://help.salesforce.com/s/articleView?id=data.c360_a_batch_transform_transformation_overview.htm

Always re-verify formula functions and node parameters against the live docs before
finalising generated JSON. The BDT parser is strict — missing `sources`, missing
`AS` aliases in formulas, or unknown `action` strings will fail import.

---

## Top-level document shape

```json
{
  "version": "56.0",
  "nodes":  { "<NODE_ID>": { ...node body... }, ... },
  "ui":     { "nodes": { "<NODE_ID>": { ...ui body... } }, "connectors": [ ... ], "hiddenColumns": [] }
}
```

Rules:
- `version` is the BDT schema version. Use `"56.0"` unless the user has a newer org.
- `nodes` is a **map keyed by node ID** (e.g. `LOAD_DATASET0`, `JOIN3`, `FILTER5`,
  `FORMULA12`, `OUTPUT2`). IDs are arbitrary but must be unique and stable —
  `connectors` and `sources` reference them by exact string.
- Every node has: `action`, `parameters`, and `sources` (array of upstream node IDs).
  Some nodes additionally have a `schema` block (typeCast, JOIN with field drop).
- `sources` is **empty `[]` only for `load` nodes**. Every other node MUST list at
  least one source. Append/Join list 2+ sources.
- `ui` is required for the canvas to render the diagram. Every node ID in `nodes`
  must have a matching entry in `ui.nodes`. Every `sources` relationship must have
  a corresponding entry in `ui.connectors` (`{source, target}`).
- Node ID prefix conventions (purely cosmetic, but follow them):
  `LOAD_DATASET#`, `JOIN#`, `APPEND#`, `FILTER#`, `FORMULA#`, `EDIT_ATTRIBUTES#`,
  `DROP_FIELDS#`, `EXTRACT#`, `AGGREGATE#`, `TRANSFORM#`, `BUCKET#`,
  `TO_MEASURE#`, `OUTPUT#`.

---

## Node catalog

### 1. `load` — Input (Data Lake Object source)

```json
"LOAD_DATASET0": {
  "action": "load",
  "parameters": {
    "dataset": { "type": "dataLakeObject", "name": "<DLO_API_NAME>__dll" },
    "sampleDetails": { "type": "TopN", "dataspace": "<DATASPACE>" },
    "fields": ["Field1__c", "Field2__c", "Id__c"]
  },
  "sources": []
}
```

- `dataset.type` is almost always `"dataLakeObject"`. DMOs as inputs use `"dataModelObject"`.
- `dataspace` defaults to `"default"` unless the user has named dataspaces.
- `fields` is the explicit projection. Always include the join keys you'll need downstream.

### 2. `join` — Combine on keys

```json
"JOIN0": {
  "action": "join",
  "parameters": {
    "joinType": "LOOKUP",                     // LOOKUP | INNER | OUTER | LEFT | RIGHT
    "leftKeys":  ["LeftKeyField__c"],
    "rightQualifier": "Acct",                 // prefix for right-side fields downstream
    "rightKeys": ["Id__c"]
  },
  "schema": {                                  // optional — drop unused right-side fields
    "slice": {
      "mode": "DROP",
      "ignoreMissingFields": true,
      "fields": ["Acct.UnusedField__c"]
    }
  },
  "sources": ["<LEFT_NODE_ID>", "<RIGHT_NODE_ID>"]
}
```

- `sources` order **matters**: first = left, second = right.
- Downstream nodes must reference right-side fields as `<rightQualifier>.<FieldName>`.
- Multi-key joins: arrays of equal length, paired by index.
- See "Join Operations" doc for semantics of each `joinType`.

### 3. `appendV2` — Stack rows from multiple sources

```json
"APPEND0": {
  "action": "appendV2",
  "parameters": {
    "fieldMappings": [
      { "top": "FieldFromSource1__c",  "bottom": "FieldFromSource2__c" },
      { "top": "Amount__c",            "bottom": "Revenue__c" }
    ]
  },
  "sources": ["<TOP_NODE_ID>", "<BOTTOM_NODE_ID>"]
}
```

- Two-source append; `top` = first source, `bottom` = second source. For 3+ sources,
  chain APPENDs (output of APPEND0 → APPEND1 with the next dataset).
- Map every column you want carried forward; un-mapped columns are dropped.
- Field types of `top` and `bottom` must match.

### 4. `filter` — Row filtering

```json
"FILTER0": {
  "action": "filter",
  "parameters": {
    "filterExpressions": [
      {
        "field":    "Status__c",
        "operator": "EQUAL",                  // EQUAL | NOT_EQUAL | IN | NOT_IN | GREATER | GREATER_EQUAL | LESS | LESS_EQUAL | IS_NULL | IS_NOT_NULL | LIKE | BETWEEN
        "operands": ["Active"],
        "type":     "TEXT"                    // TEXT | NUMBER | DATE | DATETIME | BOOLEAN
      }
    ]
  },
  "sources": ["<UPSTREAM>"]
}
```

- Multiple `filterExpressions` are combined with **AND**.
- `IN` / `NOT_IN` take multiple operands; `BETWEEN` takes exactly two.

### 5. `formula` — Computed columns

```json
"FORMULA0": {
  "action": "formula",
  "parameters": {
    "expressionType": "SQL",
    "fields": [
      {
        "name": "Amount_USD",
        "label": "Amount in USD",
        "formulaExpression": "Amount__c * \"Curr.ConversionRate__c\"",
        "businessType": "NUMBER",            // NUMBER | TEXT | DATE | DATE_ONLY | DATETIME | BOOLEAN
        "precision": 16,                      // NUMBER only
        "scale": 2,                           // NUMBER only
        "format": "dd/MM/yyyy",              // DATE/DATETIME only
        "defaultValue": ""
      }
    ]
  },
  "sources": ["<UPSTREAM>"]
}
```

Formula expression rules (BDT SQL dialect — Spark-SQL-like):
- Reference qualified columns from joins with **double-quoted** identifiers:
  `"Acct.Name__c"`. Bare local columns can be unquoted: `Amount__c`.
- String literals use **single quotes**: `'Y'`.
- Supported scalar functions (verify against the Transformations doc):
  `case when ... then ... else ... end`, `coalesce()`, `nvl()`, `cast(x as type)`,
  `concat()`, `substring()`, `length()`, `trim()`, `upper()`, `lower()`,
  `replace()`, `regexp_replace()`,
  `to_date(str, fmt)`, `to_timestamp(str)`, `date_add()`, `date_sub()`,
  `year()`, `month()`, `day()`, `current_date()`, `current_timestamp()`,
  `round()`, `floor()`, `ceil()`, `abs()`.
- Multi-line SQL is allowed inside `formulaExpression` (use `\n` in JSON).
- One `FORMULA` node can output **multiple** new fields by adding multiple entries
  to `fields[]`.

### 6. `schema` — Rename / drop columns (Edit Attributes / Drop Fields)

Two common shapes:

Drop columns:
```json
"DROP_FIELDS0": {
  "action": "schema",
  "parameters": {
    "slice": { "mode": "DROP", "ignoreMissingFields": true, "fields": ["ColA__c","ColB__c"] }
  },
  "sources": ["<UPSTREAM>"]
}
```

Rename / re-label:
```json
"EDIT_ATTRIBUTES0": {
  "action": "schema",
  "parameters": {
    "fields": [
      {
        "name": "OldName__c",
        "newProperties": {
          "name":  "NewName__c",
          "label": "New Display Label",
          "typeProperties": null
        }
      }
    ]
  },
  "sources": ["<UPSTREAM>"]
}
```

`slice.mode` can be `DROP` or `KEEP`. `KEEP` is the inverse — only listed fields survive.

### 7. `typeCast` — Convert dimension to measure (or change type)

```json
"TO_MEASURE0": {
  "action": "typeCast",
  "parameters": {
    "fields": [
      {
        "name": "Revenue__c",
        "newProperties": {
          "name":  "Revenue_to_measure__c",
          "label": "Revenue",
          "typeProperties": {
            "type": "NUMBER",
            "precision": 16,
            "scale": 2,
            "businessType": "NUMBER"
          }
        }
      }
    ]
  },
  "schema": {
    "slice":  { "mode": "DROP", "ignoreMissingFields": true, "fields": ["Revenue__c"] },
    "fields": [ { "name": "Revenue_to_measure__c", "newProperties": { "name": "Revenue__c" } } ]
  },
  "sources": ["<UPSTREAM>"]
}
```

The `schema` block here is the standard pattern: drop the original, then rename the
casted version back to the original name so downstream nodes don't break.

### 8. `extractGrains` — Extract YEAR/MONTH/DAY from date columns

```json
"EXTRACT0": {
  "action": "extractGrains",
  "parameters": {
    "grainExtractions": [
      {
        "source": "CreatedDate__c",
        "targets": [
          { "name": "Created_Year__c",  "label": "Year",  "grainType": "YEAR"  },
          { "name": "Created_Month__c", "label": "Month", "grainType": "MONTH" },
          { "name": "Created_Day__c",   "label": "Day",   "grainType": "DAY"   }
        ]
      }
    ]
  },
  "sources": ["<UPSTREAM>"]
}
```

`grainType` values: `YEAR`, `QUARTER`, `MONTH`, `WEEK`, `DAY`, `HOUR`, `MINUTE`.
An empty `grainExtractions: []` is also valid — used as a passthrough placeholder
before AGGREGATE in the canvas.

### 9. `aggregate` — Group-by aggregations

```json
"AGGREGATE0": {
  "action": "aggregate",
  "parameters": {
    "nodeType": "STANDARD",
    "aggregations": [
      { "name": "Total_Spend__c", "label": "Total Spend", "action": "SUM",    "source": "Amount__c"   },
      { "name": "Order_Count__c", "label": "Order Count", "action": "COUNT",  "source": "OrderId__c"  },
      { "name": "Unique_Custs__c","label": "Unique",      "action": "UNIQUE", "source": "CustomerId__c" }
    ],
    "groupings": ["CustomerId__c", "Year__c", "Month__c"]
  },
  "sources": ["<UPSTREAM>"]
}
```

Aggregate `action` values: `SUM`, `COUNT`, `AVG`, `MIN`, `MAX`, `UNIQUE` (count distinct),
`FIRST`, `LAST`. `groupings` is an ordered list of column names (qualified if from a join).

### 10. `bucket` — Map source values into bucket values

```json
"BUCKET0": {
  "action": "bucket",
  "parameters": {
    "fields": [
      {
        "name": "Month_MM",
        "type": "TEXT",
        "label": "Month Bucket",
        "bucketsSetup": {
          "sourceField": { "name": "MonthName__c", "type": "TEXT" },
          "buckets": [
            { "value": "01", "sourceValues": ["Jan"] },
            { "value": "02", "sourceValues": ["Feb"] }
          ],
          "defaultBucketValue": null,
          "nullBucketValue":    null,
          "isPassthroughEnabled": true,
          "algorithm": null
        }
      }
    ]
  },
  "sources": ["<UPSTREAM>"]
}
```

Use for value-mapping (month name → number, region → continent, score band, etc.).
For numeric ranges, `algorithm` may be set (e.g. `"RANGE"`) with bucket boundaries —
verify in current docs.

### 11. `outputD360` — Write to a target DLO/DMO

```json
"OUTPUT0": {
  "action": "outputD360",
  "parameters": {
    "type": "dataLakeObject",                // dataLakeObject | dataModelObject
    "name": "<TARGET_DLO_OR_DMO_API_NAME>__dll",
    "fieldsMappings": [
      { "sourceField": "CustomerId__c", "targetField": "Customer_ID__c" },
      { "sourceField": "Total_Spend__c", "targetField": "Total_Spend__c" }
    ],
    "writeMode": "OVERWRITE"                 // OVERWRITE | APPEND | UPSERT
  },
  "sources": ["<UPSTREAM>"]
}
```

- The **target object must already exist** in Data Cloud before the BDT can be saved.
- Every `targetField` must exist on that object; types must be compatible.
- `writeMode: UPSERT` requires the target to have a primary key configured.

---

## The `ui` block

The canvas needs visual metadata for every node. Minimum per node:

```json
"ui": {
  "nodes": {
    "LOAD_DATASET0": {
      "label": "Customer DLO",
      "description": "",
      "type": "LOAD_DATASET",                // matches action — see mapping below
      "top":  100,
      "left": 100,
      "parameters": {                          // load-only
        "sampleSize": 500,
        "sampleDetails": { "type": "TopN", "dataspace": "default" }
      }
    },
    "JOIN0":   { "label": "Join Customer + Orders", "type": "JOIN",   "top": 100, "left": 400 },
    "FILTER0": { "label": "Active only",            "type": "FILTER", "top": 100, "left": 700 },
    "OUTPUT0": { "label": "Write to Customer Summary", "type": "OUTPUT", "top": 100, "left": 1300 }
  },
  "connectors": [
    { "source": "LOAD_DATASET0", "target": "JOIN0" },
    { "source": "LOAD_DATASET1", "target": "JOIN0" },
    { "source": "JOIN0",         "target": "FILTER0" },
    { "source": "FILTER0",       "target": "OUTPUT0" }
  ],
  "hiddenColumns": []
}
```

Action → UI `type` mapping:

| `action` (in `nodes`) | `type` (in `ui.nodes`) |
|------------------------|--------------------------|
| `load`                 | `LOAD_DATASET`           |
| `join`                 | `JOIN`                   |
| `appendV2`             | `APPEND`                 |
| `filter`               | `FILTER`                 |
| `formula`              | `FORMULA`                |
| `schema` (drop)        | `DROP_FIELDS`            |
| `schema` (rename)      | `EDIT_ATTRIBUTES`        |
| `typeCast`             | `TO_MEASURE`             |
| `extractGrains`        | `EXTRACT`                |
| `aggregate`            | `AGGREGATE`              |
| `bucket`               | `BUCKET`                 |
| `outputD360`           | `OUTPUT`                 |

Lay nodes left-to-right in the order data flows. Use `top`/`left` increments of ~140
horizontally and ~140 vertically to keep the canvas readable.

You may also wrap a sub-graph (e.g. a formula + drop) inside a "compound" `TRANSFORM`
node in the UI:

```json
"TRANSFORM0": {
  "label": "Schedule date prep",
  "type":  "TRANSFORM",
  "top":   500, "left": 600,
  "graph": {
    "FORMULA0":     { "parameters": { "type": "BASE_FORMULA_UI" }, "label": "Compute date" },
    "DROP_FIELDS0": { "label": "Drop Columns" }
  },
  "connectors": [
    { "source": "FORMULA0", "target": "DROP_FIELDS0" }
  ]
}
```

This is purely cosmetic grouping; the underlying `nodes` map and global `connectors`
still drive execution.

---

## End-to-end minimal example

A complete BDT that loads two DLOs, joins them, filters, computes a USD amount,
aggregates, and writes to a target DLO:

```json
{
  "version": "56.0",
  "nodes": {
    "LOAD_DATASET0": {
      "action": "load",
      "parameters": {
        "dataset": { "type": "dataLakeObject", "name": "Order__dll" },
        "sampleDetails": { "type": "TopN", "dataspace": "default" },
        "fields": ["Id__c","CustomerId__c","Amount__c","CurrencyCode__c","CreatedDate__c"]
      },
      "sources": []
    },
    "LOAD_DATASET1": {
      "action": "load",
      "parameters": {
        "dataset": { "type": "dataLakeObject", "name": "Currency__dll" },
        "sampleDetails": { "type": "TopN", "dataspace": "default" },
        "fields": ["Code__c","RateToUSD__c"]
      },
      "sources": []
    },
    "JOIN0": {
      "action": "join",
      "parameters": {
        "joinType": "LOOKUP",
        "leftKeys":  ["CurrencyCode__c"],
        "rightQualifier": "Curr",
        "rightKeys": ["Code__c"]
      },
      "sources": ["LOAD_DATASET0","LOAD_DATASET1"]
    },
    "FILTER0": {
      "action": "filter",
      "parameters": {
        "filterExpressions": [
          { "field": "Amount__c", "operator": "GREATER", "operands": ["0"], "type": "NUMBER" }
        ]
      },
      "sources": ["JOIN0"]
    },
    "FORMULA0": {
      "action": "formula",
      "parameters": {
        "expressionType": "SQL",
        "fields": [
          {
            "name": "Amount_USD__c",
            "label": "Amount USD",
            "formulaExpression": "Amount__c * \"Curr.RateToUSD__c\"",
            "businessType": "NUMBER",
            "precision": 16, "scale": 2,
            "defaultValue": ""
          }
        ]
      },
      "sources": ["FILTER0"]
    },
    "AGGREGATE0": {
      "action": "aggregate",
      "parameters": {
        "nodeType": "STANDARD",
        "aggregations": [
          { "name": "Total_USD__c", "label": "Total USD", "action": "SUM",   "source": "Amount_USD__c" },
          { "name": "Order_Count__c","label": "Orders",   "action": "COUNT", "source": "Id__c" }
        ],
        "groupings": ["CustomerId__c"]
      },
      "sources": ["FORMULA0"]
    },
    "OUTPUT0": {
      "action": "outputD360",
      "parameters": {
        "type": "dataLakeObject",
        "name": "Customer_Order_Summary__dll",
        "fieldsMappings": [
          { "sourceField": "CustomerId__c",  "targetField": "Customer_ID__c"  },
          { "sourceField": "Total_USD__c",   "targetField": "Total_USD__c"    },
          { "sourceField": "Order_Count__c", "targetField": "Order_Count__c"  }
        ],
        "writeMode": "OVERWRITE"
      },
      "sources": ["AGGREGATE0"]
    }
  },
  "ui": {
    "nodes": {
      "LOAD_DATASET0": { "label": "Order DLO",   "type": "LOAD_DATASET", "top": 100, "left": 100,  "parameters": { "sampleSize": 500, "sampleDetails": { "type": "TopN", "dataspace": "default" } } },
      "LOAD_DATASET1": { "label": "Currency DLO","type": "LOAD_DATASET", "top": 280, "left": 100,  "parameters": { "sampleSize": 500, "sampleDetails": { "type": "TopN", "dataspace": "default" } } },
      "JOIN0":         { "label": "Join Currency","type": "JOIN",        "top": 190, "left": 400 },
      "FILTER0":       { "label": "Amount > 0",  "type": "FILTER",       "top": 190, "left": 700 },
      "FORMULA0":      { "label": "Compute USD", "type": "FORMULA",      "top": 190, "left": 1000 },
      "AGGREGATE0":    { "label": "Sum per Customer","type": "AGGREGATE","top": 190, "left": 1300 },
      "OUTPUT0":       { "label": "Write Summary","type": "OUTPUT",      "top": 190, "left": 1600 }
    },
    "connectors": [
      { "source": "LOAD_DATASET0", "target": "JOIN0" },
      { "source": "LOAD_DATASET1", "target": "JOIN0" },
      { "source": "JOIN0",         "target": "FILTER0" },
      { "source": "FILTER0",       "target": "FORMULA0" },
      { "source": "FORMULA0",      "target": "AGGREGATE0" },
      { "source": "AGGREGATE0",    "target": "OUTPUT0" }
    ],
    "hiddenColumns": []
  }
}
```

---

## Generation checklist

Before returning JSON to the user, validate:

1. JSON is parseable (no trailing commas, matched braces, escaped quotes inside formulas).
2. Every node ID is unique. Every ID in a `sources` array exists in `nodes`.
3. Every `load` node has `sources: []`. Every other node has at least one source.
4. Every node ID has a matching entry in `ui.nodes` and the `action`→`type` mapping above.
5. Every parent→child relationship is mirrored in `ui.connectors`.
6. Every formula computed field has `name`, `label`, `formulaExpression`, `businessType`.
   NUMBER fields have `precision`/`scale`. DATE/DATETIME have `format`.
7. Aggregate node: every column referenced in `groupings` either passes through from
   upstream or is created by an upstream formula/extract/bucket.
8. Output node: target object name and every `targetField` exist in the user's org.
   Confirm with `describe_data_lake_object` / `describe_data_model_object` before
   finalising.
9. Joins: `sources[0]` is left, `sources[1]` is right, and `rightQualifier` is used
   to address right-side fields downstream.
10. No SQL comments inside `formulaExpression` (`--` and `/* */` are rejected).

## Skill workflow

When the user asks for a BDT JSON:

1. Ask only what's truly missing (sources, target, transformations, write mode, dataspace).
2. Use `list_data_lake_objects`, `describe_data_lake_object`,
   `list_data_model_objects`, `describe_data_model_object` to confirm input fields
   and target schema. Never invent field names.
3. Plan the node graph (input(s) → joins → filters → formulas → aggregations → output).
4. Emit the JSON in a single fenced ```json``` code block so the user can copy/save it.
5. Tell the user: **save as `<name>.json` and import via Data Cloud → Data Transforms
   → New → Import Definition**, then map any unresolved fields and run.
