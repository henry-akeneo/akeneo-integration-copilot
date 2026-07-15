# Pagination, Filtering, and Rate Limits

## Two pagination schemes — know which endpoint uses which

| Scheme | Endpoints | Mechanics |
|---|---|---|
| **Cursor (`search_after`)** | products, product models, assets, reference-entity records | Follow `_links.next.href` from each response; stateless, stable on large catalogs |
| **Page-based (`page`)** | families, attributes, attribute options, channels, locales, categories, association types | `?page=2&limit=100`; max `limit` is 100 |

### Cursor pagination (use for any export or full scan)

```python
url = f"{base}/api/rest/v1/products?pagination_type=search_after&limit=100"
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
