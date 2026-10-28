# US11 catalog API — #115

`GET /api/v1/products` is public and accepts the following combinable parameters.

| Parameter | Contract |
|---|---|
| `q` | Search product name or description, case insensitive; trim whitespace; maximum 200 characters. Empty or whitespace-only input does not filter. |
| `category_id` | Positive integer; includes active descendant categories. An unknown or inactive category returns no matches. |
| `seller_id` | Positive seller ID. |
| `min_price`, `max_price` | Inclusive, nonnegative integer VND bounds on the displayed price (lowest active variant price, or base price). |
| `min_rating` | Inclusive minimum rating from 0 to 5; missing metadata counts as 0. |
| `in_stock` | Defaults to `true`; requires available stock after reservations, using active variants when variants exist. `false` includes all active products regardless of stock. |
| `sort_by` | `newest`, `bestselling`, `price_asc`, `price_desc`, or `rating_desc`. Omitted: ascending product ID. Ties use product ID for deterministic pagination. |
| `page` | Positive integer, default 1. Requests beyond the final page return that final page. |
| `page_size` | Integer from 1 to 100, default 20. |

Inactive products, including listings deleted through the seller API, never appear.
The query uses the same filters for the count and returned products.

For existing clients, `search`, `sort`, and `limit` remain supported. When both names
are supplied, `q`, `sort_by`, and `page_size` take precedence respectively, including
an explicitly empty `q`. All supplied parameter types and bounds are validated.

Example:

```text
/api/v1/products?q=laptop&category_id=1&min_price=10000000&max_price=20000000&min_rating=4&in_stock=true&sort_by=price_asc&page=1&page_size=10
```

The response contains `data` and `meta`. Metadata includes `current_page`,
`page_size`, `total_items`, and `total_pages`; legacy `limit` equals `page_size`
and `total` equals `total_items`. With no matches, `data` is empty, `current_page`
is 1, and both totals and `total_pages` are 0.

Invalid input returns `422` with `error.code = ERR_VALIDATION`. Reversed price
bounds additionally return messages in `error.fields.min_price` and
`error.fields.max_price`. Database failures return `500 ERR_DATABASE_FAILURE`.

Verification: `python -m pytest tests/test_catalog_discovery.py tests/test_products.py tests/test_us19_categories_variants.py`.
