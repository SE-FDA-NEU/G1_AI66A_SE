# US19 — Categories, product variants and order snapshots

Issue #111 adds hierarchical category administration, seller-managed product options,
variant-aware purchasing, and immutable purchase-time details for order history.

## Category administration

Categories remain readable through `GET /api/v1/categories`; inactive categories are
omitted. An authenticated `admin` can create or edit categories with
`POST /api/v1/categories` and `PATCH /api/v1/categories/{category_id}`, and deactivate
them with `DELETE /api/v1/categories/{category_id}`. Slugs are lowercase URL-safe
identifiers. Parent IDs must refer to active categories, hierarchy updates reject cycles,
and a parent with active children cannot be deactivated. Category rows are retained so
existing product metadata and orders are not detached.

## Product variants

Sellers manage options for their own listings with:

- `GET` and `POST /api/v1/seller/products/{product_id}/variants`
- `PATCH` and `DELETE /api/v1/seller/products/{product_id}/variants/{variant_id}`

Each option has a shop-unique normalized SKU, name, integer-VND price, independent stock,
optional image, active state and inventory version. `DELETE` deactivates the option.
Seller updates are ownership-checked and use the version in a conditional update so a
stale edit cannot overwrite stock changed by checkout.

Product details include active options. A product that has options cannot be added as a
base-product line; the buyer must select an active option. Cart lines distinguish
`variant_id`, use its current price and stock, and support more than one option of the
same product. The detail page provides the buyer selector and an owner-only option
management panel.

## Checkout and history

Checkout conditionally decrements the selected option's stock using its version and
available-stock predicate. Products without options retain the existing product-level
inventory behavior. Cancellation and restockable returns restore stock to the exact
product or option that was purchased.

`order_items` stores the product name, option name and image observed at purchase time;
`unit_price` remains the existing integer-VND purchase snapshot. Buyer receipts and seller
order views prefer these saved values, so later listing edits do not rewrite order
history.

Database initialization adds the category active flag and snapshot fields, creates the
variant table, and rebuilds legacy SQLite cart lines to replace the old
`(buyer_id, product_id)` uniqueness rule with uniqueness that includes the optional
variant. Existing cart rows are copied as base-product lines and old order rows are
backfilled from their current product data.

## Verification

Run the focused Python regression suite with:

```powershell
python -m pytest tests/test_us19_categories_variants.py tests/test_cart_api.py tests/test_cart_service.py tests/test_checkout.py tests/test_catalog_discovery.py tests/test_seller_products.py tests/test_return_refund.py tests/test_database.py -q
```

Exercise the browser script's option selection and login-return behavior with:

```powershell
node tests/product_detail_variants.mjs
```
