# US06 - Seller creates a product listing

**Issue:** #18  
**Priority:** P0 - Must have  
**Story Points:** 5  
**Related route:** `/seller/products/new`

## 1. User Story

As a seller, I want to create a product listing, so that buyers can discover and purchase my products.

---


## 2. Required Product Fields

A seller must provide the following information when creating a product:

- Product name
- Product description
- Product price
- Stock quantity
- Product image

The system also associates the product with the authenticated seller.

The seller identity must not be trusted from user-provided form data.

---


## 3. Product Validation Rules

### Product name

- Required.
- Must not be empty after trimming whitespace.

### Description

- Required.
- Must not be empty after trimming whitespace.

### Price

- Required.
- Must be numeric.
- Must be strictly greater than zero.

Therefore:

`price > 0`

### Stock quantity

- Required.
- Must be an integer.
- Must be greater than or equal to zero.

Therefore:

`stockQuantity ∈ Integer`

`stockQuantity >= 0`

A stock quantity of zero is valid, but the product is considered out of stock.

### Product image

A product image must be provided using the image mechanism selected by the application architecture.

The exact storage mechanism is deferred to the implementation/design milestone.

---


## 4. Seller Authorization

Only an authenticated seller may access product creation.

The authorization flow is:

```text
Request /seller/products/new
          |
          v
Authenticated?
     |          |
    No         Yes
     |          |
 Reject      Role == Seller?
                  |        |
                 No       Yes
                  |        |
                Reject   Allow
```

An unauthenticated user must not be allowed to create products.

An authenticated user without seller privileges must also be denied access.

---


## 5. Product Ownership

### BR5 - Seller product ownership

Every newly created product belongs to the authenticated seller who created it.

The product owner must be derived from the authenticated identity.

Conceptually:

`sellerId = authenticatedUser.id`

The application must not trust an arbitrary `sellerId` provided by the client.

This prevents one seller from creating or managing products on behalf of another seller.

---


## 6. Product Creation Flow

1. Seller opens `/seller/products/new`.
2. System verifies seller authentication and authorization.
3. Seller enters product information.
4. Seller submits the product form.
5. System validates all required fields.
6. System validates price and stock quantity.
7. System associates the product with the authenticated seller.
8. If all validations succeed, the product is created.
9. The seller receives confirmation that the product was created.
10. The product becomes available according to its stock state.

---


## 7. Invalid Input Behaviour

If any required field is invalid:

- the product must not be created;
- no partial product record should remain;
- valid user-entered values may remain available in the form;
- invalid fields must be identified clearly.

Examples include:

- missing name;
- missing description;
- missing image;
- price equal to or less than zero;
- negative stock;
- non-integer stock quantity.

---


## 8. Stock and Marketplace Visibility

A product with:

`stockQuantity > 0`

is available for purchase.

A product with:

`stockQuantity = 0`

is out of stock.

Creating a product with zero stock is allowed because the current acceptance criteria prohibit negative stock, not zero stock.

However, zero-stock products must follow the marketplace availability rules defined by US01 and US02.

They must not be purchasable until stock becomes available.

---


## 9. Product Creation Flow Diagram

```text
/seller/products/new
        |
        v
Check authentication
        |
        +---- Invalid ----> Deny access
        |
        v
Check seller role
        |
        +---- Invalid ----> Deny access
        |
        v
Enter product data
        |
        v
Validate required fields
        |
        +---- Invalid ----> Show field errors
        |
        v
Validate price and stock
        |
        +---- Invalid ----> Reject creation
        |
        v
Assign authenticated seller as owner
        |
        v
Create product
        |
        v
Creation confirmation
```

---

## 10. Acceptance Criteria Coverage

### AC1

An authenticated seller submitting valid product data creates a new product.

Covered by Sections 2, 4, 5 and 6.

### AC2

Missing required information causes the request to be rejected and invalid fields to be identified.

Covered by Sections 3 and 7.

### AC3

Negative price or stock prevents product creation.

Covered by Sections 3 and 7.

The requirement is strengthened so that price must be strictly positive.

### AC4

A non-seller cannot access product creation.

Covered by Section 4.

---
## 11. Runtime contract (#81)

Sections 1-10 are the Milestone 1 specification from issue #18. This section records
what issue #81 built and the decisions the specification left open.

### Image mechanism

The listing stores an image **URL**; no file is uploaded. The form field is labelled
"Image URL" and is required. The server accepts an absolute `http://` or `https://`
URL with a host, up to 2048 characters, and never downloads it. A URL that is valid
but cannot be loaded keeps the listing: the catalog and the product page show the
existing placeholder image instead. Products seeded earlier keep their relative
`/images/...` paths; the rule applies to new listings only.

### Request and validation

`POST /api/v1/seller/products` takes JSON. Strings are trimmed before they are checked;
unknown fields are refused.

| Field | Rule |
|---|---|
| `name` | Text, 1-200 characters after trimming |
| `description` | Text, 1-3000 characters after trimming |
| `price` | JSON integer VND, `1` to `1000000000` |
| `stock_quantity` | JSON integer, `0` to `1000000` |
| `image_url` | Absolute http(s) URL, at most 2048 characters |

Booleans, fractions (including `1.0`), numeric strings and `null` are refused for
price and stock. The upper bounds are technical guardrails, not business rules from
the issue: price x stock stays below JavaScript's `Number.MAX_SAFE_INTEGER`, so the
form and cart totals never lose precision.

### Server-owned fields

The server sets `seller_id` from the token (BR5), generates `code`, and sets
`reserved_stock = 0`, `version = 1` and `is_active = true`. A request that sends any
of `id`, `code`, `seller_id`, `reserved_stock`, `version` or `is_active` is refused
with `422`. A listing with stock 0 is still active: it has a product page that shows
"Out of stock" and stays out of the catalog until it has stock.

### Product code

Codes are `P-` followed by 18 random upper-case hex characters (20 characters, the
column size), for example `P-6E1059D348A4CB729F`. The UNIQUE constraint on
`products.code` guarantees uniqueness. When an insert fails because the code is
already taken, the service tries a new code, at most three times, then answers
`409 ERR_CONCURRENCY_CONFLICT` with nothing written. Any other database failure is
rolled back and answers `500 ERR_DATABASE_FAILURE`.

### Responses

| Situation | Response |
|---|---|
| Valid seller request | `201`, `{ "data": { id, code, seller_id, name, description, price, stock_quantity, reserved_stock, image_url, is_active, version } }` |
| No token, invalid or expired token | `401 ERR_AUTH_REQUIRED` / `ERR_INVALID_TOKEN` |
| Buyer token | `403 ERR_SELLER_REQUIRED` |
| Invalid fields | `422 ERR_VALIDATION`; `error.fields` maps each field to its messages, several fields at once |
| Body is not a JSON object, or contains fields the client may not send | `422 ERR_VALIDATION`; messages under `error.fields._form` |
| Product code still collides after three attempts | `409 ERR_CONCURRENCY_CONFLICT` |
| Database failure | `500 ERR_DATABASE_FAILURE` |

Validation messages never repeat the submitted values. No error writes a row.

### Form (`/seller/products/new`)

The page is a public HTML shell; the API enforces the seller role. A guest is sent to
`/login?return_to=%2Fseller%2Fproducts%2Fnew`; a buyer sees a forbidden message and
the form stays disabled. The page checks each field before sending, then shows the
server's `error.fields` beside the matching inputs and request-level errors in the
summary. Entered values are kept after every failure. A request that times out is
reported as unconfirmed and is never resent automatically, because the listing may
already exist. On success the page shows the product name, its code, and links to
**View product** (`/products/{code}`) and **Continue browsing**.

Tests and evidence: [docs/evidence/us06.md](evidence/us06.md).
