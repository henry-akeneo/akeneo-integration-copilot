# Attribute Value Formats (REST API)

Every value is `{ "locale": ..., "scope": ..., "data": ... }`. This file
covers the `data` shape per attribute type, using REST API key names
(`scope`, not the MCP tools' `channel`).

## The locale/scope matrix

| Attribute config | locale | scope | Example value entry |
|---|---|---|---|
| plain | `null` | `null` | `{"locale": null, "scope": null, "data": ...}` |
| localizable | `"en_US"` | `null` | one entry per locale |
| scopable | `null` | `"ecommerce"` | one entry per channel |
| localizable + scopable | `"en_US"` | `"ecommerce"` | one entry per locale×channel |

Sending a locale on a non-localizable attribute (or a scope on a
non-scopable one) is a 422. Sending `null` where a value is required is
also a 422. There is no partial credit: check the attribute definition.

## Per-type `data` shapes

### Text (`pim_catalog_text`) and Textarea (`pim_catalog_textarea`)

```json
"name": [{ "locale": "en_US", "scope": null, "data": "Organic Cotton Tee" }]
```

Textarea may contain HTML if the attribute is configured as rich text.

### Identifier (`pim_catalog_identifier`)

The SKU. One per product, never localizable/scopable:

```json
"sku": [{ "locale": null, "scope": null, "data": "TS-001-BLK-M" }]
```

### Number (`pim_catalog_number`)

**`data` is a string, not a JSON number.** This is the single most common
422 in generated code:

```json
"thread_count": [{ "locale": null, "scope": null, "data": "180" }]
```

### Boolean (`pim_catalog_boolean`)

A real JSON boolean (not `"true"`):

```json
"is_organic": [{ "locale": null, "scope": null, "data": true }]
```

### Date (`pim_catalog_date`)

ISO 8601 date, no time component:

```json
"release_date": [{ "locale": null, "scope": null, "data": "2026-09-01" }]
```

### Simple select (`pim_catalog_simpleselect`)

`data` is one **option code** (must exist as an option on the attribute):

```json
"color": [{ "locale": null, "scope": null, "data": "black" }]
```

### Multi select (`pim_catalog_multiselect`)

`data` is an array of option codes:

```json
"materials": [{ "locale": null, "scope": null, "data": ["cotton", "elastane"] }]
```

### Price collection (`pim_catalog_price_collection`)

`data` is an array of `{amount, currency}` objects. **`amount` is a
string.** Currencies must be activated on the instance (and on the channel
if scopable):

```json
"price": [{
  "locale": null, "scope": "ecommerce",
  "data": [
    { "amount": "29.99", "currency": "USD" },
    { "amount": "27.99", "currency": "EUR" }
  ]
}]
```

### Metric (`pim_catalog_metric`)

`data` is `{amount, unit}`. **`amount` is a string**; `unit` must belong to
the attribute's measurement family (e.g. `GRAM`, `KILOGRAM` for Weight):

```json
"weight": [{ "locale": null, "scope": null, "data": { "amount": "180", "unit": "GRAM" } }]
```

### Media file (`pim_catalog_image`, `pim_catalog_file`)

`data` is a media-file **code/path returned by the media-files endpoint**.
You cannot inline binary content in a product payload — upload via
`POST /api/rest/v1/media-files` first (multipart), then reference:

```json
"main_image": [{ "locale": null, "scope": null, "data": "a/b/c/abc123_tshirt.jpg" }]
```

### Asset collection (`pim_catalog_asset_collection`)

`data` is an array of **asset codes** from the Asset Manager:

```json
"gallery": [{ "locale": null, "scope": "ecommerce", "data": ["ts001_front", "ts001_back"] }]
```

### Reference entity, single link (`akeneo_reference_entity`)

`data` is one **record code**:

```json
"brand": [{ "locale": null, "scope": null, "data": "acme_apparel" }]
```

### Reference entity, multiple links (`akeneo_reference_entity_collection`)

```json
"designers": [{ "locale": null, "scope": null, "data": ["j_doe", "k_smith"] }]
```

### Table (`pim_catalog_table`)

`data` is an array of row objects keyed by column code (SaaS feature):

```json
"nutrition": [{ "locale": null, "scope": null, "data": [
  { "ingredient": "cotton", "percentage": 95 },
  { "ingredient": "elastane", "percentage": 5 }
]}]
```

## Clearing a value

Send the entry with `"data": null` for the exact locale/scope combination.
Omitting the attribute leaves it untouched (PATCH is a merge).
