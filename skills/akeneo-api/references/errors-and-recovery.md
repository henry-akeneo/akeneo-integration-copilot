# Errors, Recovery, and Events

## Status codes in Akeneo terms

| Code | Meaning here | What to do |
|---|---|---|
| 401 | Token expired or credentials wrong | Refresh the OAuth token (they last ~1h); if refresh fails, credentials are bad — stop, don't loop |
| 403 | Connection lacks permission for this endpoint/ACL | Fix the connection's role/permissions in the PIM UI; retrying is pointless |
| 404 | Entity doesn't exist (or the endpoint isn't available on this edition) | Check the code against the schema cache; asset/ref-entity endpoints are SaaS/EE-only |
| 413 | Payload too large | Reduce batch size |
| 415 | Wrong `Content-Type` | Bulk endpoints need `application/vnd.akeneo.collection+json`; single upserts `application/json` |
| 422 | **Schema violation** — unknown attribute, wrong locale/scope, bad `data` shape, missing option | Diff payload against the schema cache; fix the payload. Retrying unchanged will fail forever |
| 429 | Rate limited | Honor `Retry-After`, back off, resume (see pagination-and-limits.md) |
| 5xx | Server-side hiccup | Retry with backoff, max a few attempts, then surface the error |

## 422: read the response body

Akeneo 422 bodies tell you exactly what's wrong:

```json
{
  "code": 422,
  "message": "Validation failed.",
  "errors": [
    {
      "property": "values",
      "message": "Attribute \"product_description\" does not exist.",
      "attribute": "product_description"
    }
  ]
}
```

Parse `errors[]` and map each to a fix: unknown attribute → check schema
cache for the real code; "cannot be localized" → set `locale: null`;
"expects a string as data" → number sent as JSON number instead of string.

## Bulk writes: a 200 is not success

The bulk product endpoint (`PATCH /api/rest/v1/products-uuid`,
`Content-Type: application/vnd.akeneo.collection+json`, newline-delimited
JSON body) returns HTTP 200 with a **newline-delimited body of per-line
results**, keyed by `uuid` (the legacy identifier endpoint keys by
`identifier` instead):

```
{"line":1,"uuid":"fc24e6c3-933c-4a93-8a81-e5c703d134d5","status_code":204}
{"line":2,"uuid":"573dd613-0c7f-4143-83d5-63cc5e535966","status_code":422,"message":"Property \"group\" does not exist."}
{"line":3,"uuid":"25566245-55c3-42ce-86d9-8610ac459fa8","status_code":201}
```

Always parse every line. Pattern:

```python
results = [json.loads(line) for line in resp.text.strip().splitlines()]
failed = [r for r in results if r["status_code"] >= 400]
for f in failed:
    ref = f.get("uuid") or f.get("identifier")
    log.error("line %s (%s): %s", f["line"], ref, f.get("message"))
```

201 = created, 204 = updated, 422 = that line failed (others still applied).
Report failures per identifier; never report "sync succeeded" off the HTTP
status alone.

## Retry decision table

| Symptom | Retry? | How |
|---|---|---|
| 429 | Yes | After `Retry-After` |
| 5xx / network timeout | Yes | Exponential backoff, ≤3 attempts |
| 401 | Once | After token refresh only |
| 422 | **No** | Fix the payload first |
| 403 / 404 | **No** | Fix permissions / codes first |
| Bulk line failed with 422 | **No** for that line | Requeue only after payload fix; don't resend the whole batch blindly |

## Events and webhooks (SaaS Event Platform)

Akeneo SaaS delivers `product.created` / `product.updated` /
`product.deleted` (and product-model equivalents) via the **Event
Platform** to an HTTPS endpoint or Pub/Sub subscription.

- Delivery is **at-least-once and unordered**: consumers must be
  idempotent and must not assume event order reflects update order.
- Events carry identifiers, not full payloads — fetch current state via
  the REST API on receipt ("thin events"). The product may have changed
  again (or been deleted) between the event and your fetch; treat the
  fetch result as truth, not the event.
- Verify the HMAC signature header on incoming webhooks before trusting
  the body; reject unsigned requests.
- Respond 2xx quickly (queue work, don't process inline) — slow consumers
  get retries, which compounds into duplicate processing.
- PaaS/CE uses the older "Events API" connection settings; semantics
  (at-least-once, thin-ish payloads) are similar but configuration differs.
