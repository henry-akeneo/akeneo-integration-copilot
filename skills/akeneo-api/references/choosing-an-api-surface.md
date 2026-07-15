# Choosing the API surface: REST, GraphQL, or Events

Akeneo SaaS exposes three integration surfaces. Picking the wrong one is a
shape problem you pay for over the whole integration — decide before
writing code. (Akeneo's own recommendation, from the GraphQL docs:)

| Integration need | Use |
|---|---|
| Read-only (exports, feeds, storefront data) | **GraphQL** — one query replaces chains of REST calls |
| Writing data (any amount) | **REST** — GraphQL has no mutations |
| Complex relation-fetching + writing | **Both**: GraphQL to read, REST to write |
| React to changes instead of polling | **Event Platform** + REST/GraphQL fetch on receipt |

## GraphQL API (read-only)

The killer use case: fetching a product **and its related data** — labels,
family, categories, asset records, reference-entity records — in one call
where REST needs a call per relation. It wraps the GET REST endpoints, so
schema codes are the same and **rule zero still applies**: verify every
attribute/family/channel/locale code against the fetched schema before
writing queries.

Essentials (verified against api.akeneo.com/graphql/ docs):

- Endpoint: `https://graphql.sdk.akeneo.cloud` (POST; also an in-browser
  IDE at that URL). Auth headers: `X-PIM-URL`, `X-PIM-CLIENT-ID`,
  `X-PIM-TOKEN` — the token is a normal REST API token (connection or App
  token), obtainable via a dedicated `token(...)` GraphQL query.
- Available queries: `products`, `productModels`, `categories`,
  `families`, `attributes`, `attributeOptions`, `channels`, `locales`,
  `currencies`, `measurementFamilies`, `assetFamilies`, `assetsRecords`,
  `referenceEntities`, `referenceEntitiesRecords`, `systemInformation`.
- Useful `products` arguments: `locales`, `channel`, `currencies`,
  `search` (same JSON filter syntax as REST, string-encoded),
  `categories`/`families`/`uuid` (shorthand filters), `parent` /
  `noParent: YES` (variants of a model / simple products only),
  `attributesToLoad` (the GraphQL analogue of the REST `attributes`
  param — always set it on large catalogs), `convertMeasurements`.
- **Naming**: GraphQL uses `channel`, like the MCP tools — not `scope`.
  Same trap as everywhere: only raw REST payloads say `scope`.
- Pagination is cursor-style: request `links { next }` and pass it as
  `page` on the next query; never construct cursors.

Limits (they adapt over time — on errors, re-check the live docs):

- Rate limit: **500 requests / 10s per PIM URL**.
- **Query cost limit 5000** — cost grows with `limit` × requested fields;
  the error says the found cost. Reduce `limit` or fields, don't retry.
- **Depth limits per query** (e.g. `products` 8, `productModels` 7,
  `assetsRecords` 3) — every opened bracket is a level.
- Cost/depth errors are schema-independent 4xx-style errors: fix the
  query shape; retrying unchanged fails forever (same rule as 422).

## Event Platform (inbound)

For reacting to PIM changes (`product.created/updated/deleted`, etc.)
instead of polling. Delivery semantics, HMAC verification, and the
thin-event fetch-on-receipt pattern are documented in
[errors-and-recovery.md](errors-and-recovery.md#events-and-webhooks-saas-event-platform).
Pair it with GraphQL on receipt when the consumer needs the product plus
its relations.

Full and current references: <https://api.akeneo.com/graphql/getting-started.html>
and <https://api.akeneo.com/event-platform/overview.html>.
