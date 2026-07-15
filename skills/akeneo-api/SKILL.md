---
name: akeneo-api
description: >
  Knowledge of the Akeneo PIM REST API for building integrations: attribute
  value formats, locale and channel scoping, pagination, rate limits, upsert
  semantics, and error recovery. Use this skill whenever writing, reviewing,
  or debugging any code that calls an Akeneo API, generates product payloads,
  syncs product data to or from a PIM, or handles Akeneo events/webhooks --
  even if the user just says "the PIM" or "product sync" without naming Akeneo.
---

# Akeneo API Integration Knowledge

This skill targets **Akeneo SaaS** (the current cloud product and its REST
API). Most of it applies to PaaS/Community Edition too; where they differ
(rate limits, events platform), the reference files say so.

## Rule zero: never invent schema

Attribute codes, family codes, channels, and locales are **instance-specific
configuration**, not standard fields. There is no such thing as "the usual
Akeneo attributes." Before generating any code that reads or writes product
data:

1. Fetch the real schema via the Akeneo MCP tools (families, attributes,
   channels, locales) — or from `demo/sample-schema.json` in this plugin
   when running in demo mode (check `.akeneo-mode.json` in the project root).
2. If an attribute the task needs does not exist, **say so** — do not guess
   a code. Offer the closest real codes instead.

## Schema cache contract

After fetching the schema, write it to `.akeneo-schema-cache.json` in the
project root. The plugin's write-guard hook validates outbound payloads
against this file and **blocks all writes when it is missing**. Format:

```json
{
  "fetched_at": "2026-07-15T10:00:00Z",
  "source": "live",
  "locales": ["en_US", "fr_FR"],
  "channels": [
    { "code": "ecommerce", "locales": ["en_US", "fr_FR"], "currencies": ["USD", "EUR"] }
  ],
  "families": {
    "tshirts": { "attributes": ["sku", "name", "description"], "attribute_as_label": "name" }
  },
  "attributes": {
    "description": { "type": "pim_catalog_textarea", "localizable": true, "scopable": true },
    "materials":   { "type": "pim_catalog_multiselect", "localizable": false, "scopable": false, "options": ["cotton", "polyester"] }
  }
}
```

`source` is `"live"` or `"demo"`. Include `options` for select attributes and
`metric_family`/`default_metric_unit` for metrics when available.

## Product value structure (the #1 source of bugs)

Every product value in a REST payload is an object with `locale`, `scope`,
and `data` keys:

```json
"values": {
  "description": [
    { "locale": "en_US", "scope": "ecommerce", "data": "..." }
  ]
}
```

- `locale` is `null` unless the attribute is **localizable**
- `scope` is `null` unless the attribute is **scopable** (scope = channel code)
- Sending a locale for a non-localizable attribute returns a 422 (and vice versa)
- **Naming trap:** the raw REST API calls this key `scope`; the Akeneo MCP
  tools call the same concept `channel`. Generated REST code must use `scope`.
- Number attribute `data` is a **string** (`"45.5"`), booleans are real
  booleans, multiselects are arrays, prices and metrics are objects — the
  shape of `data` depends on attribute type. Read
  [references/attribute-value-formats.md](references/attribute-value-formats.md)
  before constructing payloads for anything beyond plain text.

## Reading data

- Prefer `search_after` (cursor) pagination for any export or full scan;
  page-based pagination is capped and degrades on large catalogs. Products,
  product models, assets, and reference-entity records are cursor-based;
  structure endpoints (families, attributes, channels) are page-based,
  max 100 per page.
- Filter server-side with the `search` query param instead of fetching all
  and filtering in code. Filter syntax and operator support vary by field.
- Request only needed attributes with the `attributes` param on product
  endpoints to cut payload size (it filters `values` only — system
  properties like `family` and `categories` are always returned).
- Details, filter operator tables, and worked examples:
  [references/pagination-and-limits.md](references/pagination-and-limits.md)

## Writing data

- Upserts are `PATCH`; the bulk endpoint accepts newline-delimited JSON
  (`Content-Type: application/vnd.akeneo.collection+json`) and returns a
  **per-line status** — a 200 on the request does NOT mean every product
  succeeded. Always parse line results.
- Batch writes at ~100 items per request; never write in an unbounded loop.
- PATCH semantics are a merge: omitted attributes are untouched, but a value
  you send **replaces all values of that attribute for that locale/scope
  combination**. To clear a value, send `"data": null` explicitly.
- Respect rate limits: back off on 429 honoring `Retry-After`. Limits and
  retry patterns: [references/pagination-and-limits.md](references/pagination-and-limits.md)

## Errors

- 422 means schema violation — diff the payload against the fetched schema
  before retrying; retrying unchanged will fail forever.
- Full status-code table, bulk line-result parsing, retry decision table,
  and events/webhooks delivery semantics:
  [references/errors-and-recovery.md](references/errors-and-recovery.md)

## Checklist before presenting integration code

1. Schema fetched and cached to `.akeneo-schema-cache.json`; every
   attribute, family, channel, and locale code verified to exist
2. `locale`/`scope` keys correct per attribute definition (nulls where
   not localizable/scopable)
3. `data` shapes match attribute types (numbers as strings, price/metric
   objects, multiselect arrays)
4. Pagination via `search_after`; filtering done server-side
5. Bulk write line-results parsed; batching (~100) and 429 backoff present
6. A dry-run mode exists so the user can validate before touching real data
7. Secrets read from env vars (`AKENEO_API_URL`, `AKENEO_CLIENT_ID`,
   `AKENEO_CLIENT_SECRET`, `AKENEO_USERNAME`, `AKENEO_PASSWORD`), never hardcoded
