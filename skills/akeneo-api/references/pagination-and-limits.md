# Pagination, Filtering, and Rate Limits

## Two pagination schemes — know which endpoint uses which

| Scheme | Endpoints | Mechanics |
|---|---|---|
| **Cursor (`search_after`)** | products, product models, assets, reference-entity records | Follow `_links.next.href` from each response; stateless, stable on large catalogs |
| **Page-based (`page`)** | families, attributes, attribute options, channels, locales, categories, association types | `?page=2&limit=100`; max `limit` is 100 |

### Cursor pagination (use for any export or full scan)

```python
url = f"{base}/api/rest/v1/products-uuid?pagination_type=search_after&limit=100"
while url:
    resp = session.get(url).json()
    for product in resp["_embedded"]["items"]:
        process(product)
    url = resp["_links"].get("next", {}).get("href")
```

- Never use page-based pagination for products: it is capped (~10k window)
  and response time degrades with page depth on large catalogs.
- Do not compute cursors yourself; always follow the `next` link.

### Page-based (structure endpoints only)

```python
page = 1
while True:
    resp = session.get(f"{base}/api/rest/v1/attributes?page={page}&limit=100").json()
    items = resp["_embedded"]["items"]
    if not items:
        break
    yield from items
    page += 1
```

`with_count=true` returns `items_count` but is expensive — use it once with
`limit=1` if you only need a count, never on every page.

## Server-side filtering (`search` param)

Always filter server-side; never fetch-all-then-filter. The `search` param
takes JSON: `{"field": [{"operator": "OP", "value": ...}]}`.

Commonly needed filters:

```json
{"enabled": [{"operator": "=", "value": true}]}
{"family": [{"operator": "IN", "value": ["tshirts"]}]}
{"categories": [{"operator": "IN CHILDREN", "value": ["summer"]}]}
{"updated": [{"operator": "SINCE LAST N DAYS", "value": 7}]}
{"completeness": [{"operator": ">=", "value": 85, "scope": "ecommerce"}]}
```

Attribute-value filters **require `locale` and/or `scope`** matching the
attribute's configuration:

```json
{"name": [{"operator": "CONTAINS", "value": "tee", "locale": "en_US"}]}
{"price": [{"operator": ">=", "value": 50, "currency": "USD", "scope": "ecommerce"}]}
```

Operator support varies by field type — text supports `CONTAINS`/`STARTS
WITH`; select attributes only `IN`/`NOT IN`/`EMPTY`/`NOT EMPTY`; category
and attribute **codes** only support `IN` (no `CONTAINS`).

## Trimming payloads

- `attributes=name,description,price` on product endpoints returns only
  those keys in `values`. System properties (`identifier`, `family`,
  `categories`, `enabled`, `created`, `updated`, associations) are always
  returned regardless.
- `scope=ecommerce` filters values to one channel; `locales=en_US,fr_FR`
  filters localizable values.
- Combining all three routinely cuts export payload size by 80%+.

## Response-shaping params on `GET /api/rest/v1/products-uuid`

These exist on the UUID endpoints (mostly not on the legacy identifier
one) and often replace a whole second integration pass — check them
before writing enrichment code:

| Param | What it does |
|---|---|
| `search_scope`, `search_locale` | Apply one scope/locale to every attribute filter in `search` instead of repeating it per attribute |
| `convert_measurements=true` | Convert metric values to the channel's conversion unit (requires `scope`) — beats client-side unit math |
| `with_attribute_options=true` | Include human-readable option labels alongside codes (`linked_data`) — saves fetching every option list |
| `with_completenesses=true` | Per-channel/locale completeness on each product |
| `with_quality_scores=true` | Data-quality scores per product |
| `with_root_parent=true` | Root product-model code on each variant — saves walking the parent chain |
| `with_asset_share_links`, `with_enabled_assets_only` | Asset-collection share URLs / filter out disabled assets |
| `with_readiness=scores_only\|detailed` | Readiness scores (beta, request access) |
| `with_count=true` | Total count — expensive on big catalogs; use once with `limit=1`, never per page |

Each `with_*` costs response size and server time — request only what the
integration consumes.

### Filters too big for a URL

`POST /api/rest/v1/products-uuid/search` accepts the same `search`,
`scope`, `locales`, `attributes`, and `with_*` options in a JSON **body**
— use it when a long filter (e.g. hundreds of UUIDs) would blow past URL
length limits. Pagination params stay in the query string.

## Incremental syncs (change detection)

The field-proven pattern for keeping a downstream system in sync is a
**combination**: the Event Platform for low-latency reaction, plus a
periodic `updated`-filtered poll as the safety net (events are
at-least-once, not exactly-once — a poll catches anything missed).

```json
{"updated": [{"operator": "SINCE LAST N DAYS", "value": 1}]}
```

**The `updated` gap:** a product's `updated` timestamp does not move when
a *linked entity* changes — an asset re-uploaded or a reference-entity
record edited leaves every product using it untouched, so a plain
`updated` poll silently misses changes the downstream system needs. Use
`updated_including_linked_entities` (SaaS, EE) instead:

```json
{"updated_including_linked_entities": [{"operator": "SINCE LAST N DAYS", "value": 7}]}
```

- Same datetime operators as `updated` (`=`, `>`, `<`, `BETWEEN`,
  `SINCE LAST N DAYS`, ...).
- Requires the **Linked entities update** option enabled per entity type
  in the PIM (System > Configuration) — with it disabled, changes to that
  entity type are invisible to the filter. This is a PIM admin setting,
  not something the API can inspect: **surface it to the integrator as an
  option** — "if downstream needs to react to asset or reference-entity
  changes, enable Linked entities update for those types, and this filter
  picks them up" — rather than assuming it's on or silently falling back
  to plain `updated`.
- Companion property `updated_including_linked_type` (operator `IN`,
  values `asset` / `reference_entity_record`) restricts which linked
  types count.
- Use datetime bounds from the *server's* responses (e.g. the max
  `updated` seen last run), not the client clock — clock skew and writes
  in flight during the export window cause missed or duplicated items.

## Production scale notes (beyond rate limits)

- **Writes have side effects**: bulk upserts trigger completeness
  recalculation, rules, and index updates. Symptoms are writes that
  "succeed" but appear delayed, and a PIM that slows under sustained
  bulk writing. Keep batches ~100, pace sustained imports, and don't
  treat write throughput as symmetric with read throughput.
- **Media and assets are the real bottleneck** in many integrations:
  product JSON syncs fast, but media files go through separate
  endpoints (multipart upload / binary download) with sizes that dwarf
  the product payloads. Plan media transfer as its own pipeline —
  parallelism budget, resumability, and caching by checksum — rather
  than bolting it onto the product loop.

## Rate limits and backoff

- Akeneo SaaS enforces rate limits (on the order of a few requests per
  second per connection, subject to change; PaaS/CE limits depend on the
  hosting). Do not hardcode assumptions — handle 429 wherever you call.
- On **429**: read `Retry-After` (seconds) and sleep at least that long.
  If absent, exponential backoff starting at 1s, doubling to a 60s cap,
  with jitter.
- Batch bulk writes at ~100 items per request. This keeps individual
  requests under payload limits and makes line-result handling tractable.
- Run exports and imports sequentially per connection rather than
  parallelizing aggressively; parallel writers mostly convert throughput
  into 429s.

```python
def request_with_backoff(session, method, url, **kwargs):
    delay = 1
    for attempt in range(8):
        resp = session.request(method, url, **kwargs)
        if resp.status_code != 429:
            return resp
        wait = int(resp.headers.get("Retry-After", delay))
        time.sleep(wait + random.uniform(0, 0.5))
        delay = min(delay * 2, 60)
    resp.raise_for_status()
```
