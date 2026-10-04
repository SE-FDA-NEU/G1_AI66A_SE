# REST API Design

This document defines the API contract for the P0 user stories in Milestone 1.
All endpoints use the `/api/v1` prefix and return JSON. Unless stated
otherwise, timestamps are ISO 8601 UTC strings.

### Product identifiers

Product identifiers have two distinct forms:

- `id` is the internal database primary key. It is an integer and is not used
  in public product URLs.
- `code` is the public product identifier. It is a unique string up to 20
  characters, using the existing catalog format such as `P-100`.

Product detail and cart endpoints use `productCode`/`product_code` and must
resolve the product by `Product.code`. They must not require a UUID. Other
resource identifiers follow the identifier type defined by their own database
model; this contract does not assume that every identifier is a UUID.

## Authentication and common response rules

- **Guest (G):** no access token is required.
- **User (U):** requires a valid authenticated buyer or seller access token.
- **Seller (S):** requires a valid authenticated seller token. The seller
  identity is taken from the token, never from a request body.
- Authenticated endpoints use `Authorization: Bearer <access-token>`.
- Successful collection responses use `{ "data": [...], "meta": {...} }`.
- Successful mutation responses return the created or updated resource in
  `{ "data": {...} }`.
- Errors use the common shape:

```json
{
  "error": {
    "code": "ERR_CODE",
    "message": "Human-readable explanation"
  }
}
```

## P0 endpoint contract

| Method and path | Access | Input parameters/body | Successful response | Error responses | Relevant P0 story |
|---|---|---|---|---|---|
| `GET /api/v1/products` | G | Query: `page` (positive integer, default `1`), `limit` (1-100, default `20`), optional catalog filters | `200 OK`: paginated product summaries with internal integer `id`, public `code`, `name`, `price`, `image_url`/`thumbnail_url`, `stock_quantity`, and `stock_status` | `400 Bad Request` for invalid pagination/filter values; `500 Internal Server Error` when the catalog cannot be read | US01 Browse product catalog |
| `GET /api/v1/products/{productCode}` | G | Path: `productCode` public product code, for example `P-100` | `200 OK`: one product with `id` (internal integer), `code`, full description, image, price, and current stock status | `404 Not Found` when the product code does not exist or the product is inactive; `422 Unprocessable Entity` when the code is empty or exceeds 20 characters | US02 View product details |
| `GET /api/v1/cart` | U (buyer) | No body; cart is identified by the authenticated buyer | `200 OK`: cart lines containing product IDs, names, images, unit prices, quantities, line totals, and `cart_total` | `401 Unauthorized` when the token is missing/invalid; `404 Not Found` when no active cart exists | US03 Cart management |
| `POST /api/v1/cart/items` | U (buyer) | JSON: `{ "product_code": "P-100", "quantity": 1 }` | `201 Created` for a new line, or `200 OK` when an existing line is increased; returns the updated cart | `400 Bad Request` for non-positive/non-integer quantity; `401 Unauthorized`; `404 Not Found` for an unavailable product code; `409 Conflict` when the requested quantity exceeds current stock | US03 Cart management |
| `PATCH /api/v1/cart/items/{productCode}` | U (buyer) | Path: public `productCode`; JSON: `{ "quantity": 2 }` | `200 OK`: updated cart with recalculated line and cart totals | `400 Bad Request` for invalid quantity; `401 Unauthorized`; `404 Not Found` when the cart line/product code does not exist; `409 Conflict` when stock is insufficient | US03 Cart management |
| `DELETE /api/v1/cart/items/{productCode}` | U (buyer) | Path: public `productCode`; no body | `200 OK`: updated cart after removing the line | `401 Unauthorized`; `404 Not Found` when the cart line does not exist | US03 Cart management |
| `POST /api/v1/orders` | U (buyer) | JSON: `{ "recipient_name": "...", "delivery_address": "...", "phone_number": "..." }`; items are read from the authenticated buyer's cart | `201 Created`: order ID, item snapshots, quantities, total, status, and delivery information | `400 Bad Request` for missing/invalid delivery data or an empty cart; `401 Unauthorized`; `409 Conflict` when a product is unavailable or stock changed; `500 Internal Server Error` if the transaction cannot be completed | US04 Checkout and order placement |
| `POST /api/v1/seller/products` | S | Multipart or JSON product body: `name`, `description`, `price`, `stock_quantity`, and `image`; seller comes from the token | `201 Created`: newly created product listing with seller ownership and publication status | `400 Bad Request` for empty name/description or invalid values; `401 Unauthorized`; `403 Forbidden` for a non-seller account; `422 Unprocessable Entity` for malformed fields | US06 Create product listing |
| `GET /api/v1/seller/orders` | S | Query: `status`, `from`, `to`, `page`, and `limit` (default `20`) | `200 OK`: paginated seller-owned order items only, including parent order ID, product, quantity, price, and status | `400 Bad Request` for invalid status/date/pagination; `401 Unauthorized`; `403 Forbidden` for a non-seller account | US08 Seller order management |
| `PATCH /api/v1/seller/orders/{subOrderId}/status` | S | Path: seller-owned order-item ID; JSON: `{ "status": "PROCESSING" }` | `200 OK`: updated sub-order status and transition timestamp | `400 Bad Request` with `ERR_INVALID_TRANSITION` for an invalid status transition; `401 Unauthorized`; `403 Forbidden` if the item belongs to another seller; `404 Not Found` when the sub-order does not exist | US08 Seller order management |

## Error handling

The API uses these HTTP status codes consistently:

| Status | Code examples | Condition |
|---|---|---|
| `400 Bad Request` | `ERR_INVALID_QUANTITY`, `ERR_INVALID_TRANSITION` | The request is syntactically valid but violates a business rule, such as quantity `0` or reverting a shipped sub-order to pending. |
| `401 Unauthorized` | `ERR_AUTH_REQUIRED`, `ERR_INVALID_TOKEN` | An authenticated endpoint is called without a valid bearer token. |
| `403 Forbidden` | `ERR_SELLER_REQUIRED`, `ERR_RESOURCE_OWNER` | The identity is authenticated but lacks the required seller role or does not own the requested seller resource. |
| `404 Not Found` | `ERR_PRODUCT_NOT_FOUND`, `ERR_CART_ITEM_NOT_FOUND` | The requested product, cart line, or seller sub-order does not exist or is not visible to the caller. |
| `409 Conflict` | `ERR_STOCK_EXCEEDED`, `ERR_PRODUCT_UNAVAILABLE` | The request conflicts with current inventory or availability, including a checkout race with another purchase. |
| `422 Unprocessable Entity` | `ERR_VALIDATION` | A field has the wrong format or type, such as an invalid product code, phone number, price, or stock quantity. |
| `500 Internal Server Error` | `ERR_DATABASE_FAILURE` | An unexpected database or infrastructure failure prevents the operation from completing. The response must not expose SQL details. |

## P0 coverage

The contract covers every P0 story listed in the Milestone 1 requirements:

| Story | Covered endpoints |
|---|---|
| US01 Browse product catalog | `GET /api/v1/products` |
| US02 View product details | `GET /api/v1/products/{productCode}` using public codes such as `P-100` |
| US03 Cart management | `GET`, `POST`, `PATCH`, and `DELETE /api/v1/cart...` |
| US04 Checkout and order placement | `POST /api/v1/orders` |
| US06 Create product listing | `POST /api/v1/seller/products` |
| US08 Seller order management | `GET /api/v1/seller/orders` and `PATCH /api/v1/seller/orders/{subOrderId}/status` |
