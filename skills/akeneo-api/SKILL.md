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
   when running in demo mode. Mode comes from the environment **at
   runtime**: credentials present means live. `.akeneo-mode.json` is a
   session-start hint only; never let a stale marker force demo behavior
   when real credentials exist.
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

`source` is `"live"` or `"demo"` — set it honestly. **A demo-sourced cache
is only valid in demo mode**: the hook (and any script) must refuse to
validate live data against it, and a live DISCOVER must rebuild the cache
from the instance rather than reuse a demo one. Include `options` for
select attributes involved in writes (skipping options is acceptable for
read-only work, but say so) and `metric_family`/`default_metric_unit` for
metrics when available.

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
  tools **and the GraphQL API** call the same concept `channel`. Only
  generated REST payloads use `scope`.
- Number attribute `data` is a **string** (`"45.5"`), booleans are real
  booleans, multiselects are arrays, prices and metrics are objects — the
  shape of `data` depends on attribute type. Read
  [references/attribute-value-formats.md](references/attribute-value-formats.md)
  before constructing payloads for anything beyond plain text.

## Choose the API surface first

Akeneo SaaS has three surfaces: **REST** (the only one that writes),
**GraphQL** (read-only; one query fetches a product *plus* its relations —
family, categories, assets, reference entities — where REST needs a call
per relation), and the **Event Platform** (react to changes instead of
polling). Read-heavy integration → GraphQL; any writing → REST; reacting →
events + fetch on receipt. Decision table, GraphQL essentials (auth, cost
and depth limits, available queries), and the `channel`-not-`scope`
naming note:
[references/choosing-an-api-surface.md](references/choosing-an-api-surface.md).
Rule zero applies to GraphQL queries exactly as to REST payloads.

## Reading data

- **Use the UUID product endpoints** (`/api/rest/v1/products-uuid`) — this
  is the surface Akeneo maintains and recommends: UUIDs never change even
  when SKUs do, and these endpoints carry response-shaping params the
  legacy identifier endpoint lacks. `/api/rest/v1/products` (identifier)
  exists for integrations keyed on SKU; treat it as legacy.
- Prefer `search_after` (cursor) pagination for any export or full scan;
  page-based pagination is capped and degrades on large catalogs. Products,
  product models, assets, and reference-entity records are cursor-based;
  structure endpoints (families, attributes, channels) are page-based,
  max 100 per page.
- Filter server-side with the `search` query param instead of fetching all
  and filtering in code. Filter syntax and operator support vary by field.
- For **incremental syncs**, the proven pattern is the `updated` filter
  plus the Event Platform in combination — and know that plain `updated`
  does not move when a *linked* asset or reference-entity record changes;
  `updated_including_linked_entities` covers that case. Details:
  [references/pagination-and-limits.md](references/pagination-and-limits.md)
- Request only needed attributes with the `attributes` param on product
  endpoints to cut payload size (it filters `values` only — system
  properties like `family` and `categories` are always returned).
- Details, filter operator tables, and worked examples:
  [references/pagination-and-limits.md](references/pagination-and-limits.md)

## Writing data

- Upserts are `PATCH` (`/api/rest/v1/products-uuid/{uuid}` single, or bulk
  `PATCH /api/rest/v1/products-uuid`); the bulk endpoint accepts
  newline-delimited JSON (`Content-Type: application/vnd.akeneo.collection+json`)
  and returns a **per-line status** — a 200 on the request does NOT mean
  every product succeeded. Always parse line results.
- Bulk lines support **delta category ops**: `add_categories` /
  `remove_categories` preserve existing categories, where plain
  `categories` replaces the whole list — prefer the delta ops in syncs.
- `?create_missing_options` on create/update auto-creates missing select
  options — but only for attributes with
  `enable_option_creation_during_import` enabled; don't rely on it as a
  substitute for verifying option codes.
- **Variants: the most common write bug is a value at the wrong
  enrichment level.** Each attribute is owned by one level (root model /
  sub model / variant) per the family variant; by default a PATCH on a
  variant can only set variant-owned values. `?update_parent_values=true`
  on the products-uuid PATCH lets one call update the parent model's
  values too — use it deliberately, not as a way to avoid checking which
  level owns the attribute.
- Batch writes at ~100 items per request; never write in an unbounded loop.
- PATCH semantics are a merge: omitted attributes are untouched, but a value
  you send **replaces all values of that attribute for that locale/scope
  combination**. To clear a value, send `"data": null` explicitly.
- Respect rate limits: back off on 429 honoring `Retry-After`. Limits and
  retry patterns: [references/pagination-and-limits.md](references/pagination-and-limits.md)

## Permissions fail silently (not with errors)

Two field-proven traps that produce no error message:

- **GETs return only what the connection's user group can see.** Missing
  products, locales, or attribute groups in an export usually means a
  permissions gap, not an API bug — the response is simply filtered.
  During DISCOVER, sanity-check counts against what the user expects.
- **Writes can become drafts (EE workflows).** A PATCH from a connection
  with edit-through-category rights (rather than owner rights) "succeeds"
  but creates a draft awaiting approval — live data is unchanged and
  downstream systems never see it. The response cannot tell you which
  happened, so **read-after-write**: on the first write against a new
  instance or connection, GET the product back and confirm the value is
  in its live values; if not, check `/products-uuid/{uuid}/draft` to
  confirm the draft path and fix the connection's permissions. This is a
  once-per-connection smoke test (ownership is a property of the
  connection's user group), not a per-item check — don't double the API
  traffic by re-reading every write.

## Errors

- 422 means schema violation — diff the payload against the fetched schema
  before retrying; retrying unchanged will fail forever.
- Full status-code table, bulk line-result parsing, retry decision table,
  and events/webhooks delivery semantics:
  [references/errors-and-recovery.md](references/errors-and-recovery.md)

## Beyond this skill: verify endpoints, don't remember them

This skill documents the well-trodden paths only: product reads/exports
(`GET /api/rest/v1/products-uuid` with `search_after`, filters, and
response-shaping params), structure listing (families, attributes,
attribute options, channels, locales, categories, association types —
page-based), product upserts (single and bulk NDJSON
`PATCH /api/rest/v1/products-uuid`), GraphQL essentials, and Event
Platform semantics.

For anything outside that — media files, assets, reference entities,
measurement families, catalogs-for-apps — or any parameter you are not
certain still exists, do not write REST code from memory (training
knowledge drifts behind the API):

1. Prefer the `akeneo_docs_*` MCP tools (`upsert_patterns`,
   `attribute_values`, `search_filters`, `pagination`, `workflows`) —
   Akeneo-maintained, always current.
2. If the MCP server is unavailable (demo mode: it requires credentials),
   fetch the current reference from <https://api.akeneo.com/api-reference-index.html>
   instead (WebFetch), and say in your output that the endpoint shape came
   from the public docs, not the instance.

Uncertainty about an endpoint never falls back to guessing — the same rule
zero that applies to schema applies to the API surface.

## Dry-run rules (every script gets one)

- `--dry-run` **may perform GETs** (schema, products) but **writes nothing
  to disk** — not the output file, not even the schema cache.
- Dry-run output is a **preview**: header + first N rows + a summary line
  (counts, size estimate) — never the full dataset to stdout.
- On large catalogs, surface scale before doing the work: "this catalog
  has N families / M products — export everything or filter?" Exports
  should carry `--families`, `--locales`, `--channel`, `--attributes`
  flags rather than defaulting to everything.

## Checklist before presenting integration code

1. Schema fetched and cached to `.akeneo-schema-cache.json`; every
   attribute, family, channel, and locale code verified to exist
2. `locale`/`scope` keys correct per attribute definition (nulls where
   not localizable/scopable)
3. `data` shapes match attribute types (numbers as strings, price/metric
   objects, multiselect arrays)
4. Pagination via `search_after`; filtering done server-side
5. Bulk write line-results parsed; batching (~100) and 429 backoff present
6. A dry-run mode exists (per the dry-run rules above) so the user can
   validate before touching real data
7. Secrets read from env vars (`AKENEO_API_URL` — alias `AKENEO_BASE_URL`
   — plus `AKENEO_CLIENT_ID`, `AKENEO_CLIENT_SECRET`, `AKENEO_USERNAME`,
   `AKENEO_PASSWORD`), never hardcoded; `--env-file` as the explicit
   opt-in for un-exported `.env` files
8. Live/demo mode decided from the environment at runtime; live data is
   never validated against a demo-sourced schema cache
9. Any endpoint or parameter not documented in this skill verified against
   the `akeneo_docs_*` MCP tools (or api.akeneo.com when MCP is
   unavailable), not written from memory
