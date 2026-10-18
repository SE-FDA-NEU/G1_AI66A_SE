# P0 UI Documentation (Milestone 3)

This document is the final UI contract for the six P0 stories (US01, US02, US03,
US04, US06, US08) plus the shared login and order-confirmation screens. It started
as the low-fidelity wireframes of #76 (PR #88, reviewed before implementation) and
was finalized in #85 against the screens that run on `main` after PRs #89 to #96,
together with the root entry from #83 (PR #97). Every message in quotes below is the
exact text the page or API shows; the error cases in section 3.2 are checked
against the source code by `tests/test_docs_contract.py`.

Where the running screen differs from the initial wireframe, the screen section
says so under **Changed from the initial wireframe**. Screenshots of every screen and
state are in [Milestone 3 evidence](evidence/milestone3.md).

## 1. Screen inventory and navigation

| Screen | Route | Story | Purpose | Endpoint(s) | Access | Primary CTA | Next step | Built in |
|---|---|---|---|---|---|---|---|---|
| Entry | `/` | US01 | Open the marketplace | `GET /` | Guest | None | Browsers are sent to `/products` (307); API clients get the JSON status | #83 (PR #97) |
| Product catalog | `/products` | US01 | Find active products that are in stock | `GET /api/v1/products?page=1&limit=20&search=` | Guest | Select a product card | Product detail | #77 (PR #90) |
| Product detail | `/products/{productCode}` | US02 | Decide on one product and add it to the cart | `GET /api/v1/products/{productCode}`, `POST /api/v1/cart/items` | Guest; adding needs a buyer | **Add to Cart** | `/cart`, or login then back to the detail page | #78 (PR #91) |
| Cart | `/cart` | US03 | Review lines and change quantities | `GET /api/v1/cart`, `PATCH`/`DELETE /api/v1/cart/items/{productCode}` | Buyer | **Checkout** | `/checkout` | #79 (PR #92) |
| Checkout | `/checkout` | US04 | Enter delivery details and place the order | `GET /api/v1/auth/me`, `GET /api/v1/cart`, `POST /api/v1/orders` | Buyer | **Confirm order** | Order confirmation | #80 (PR #94) |
| Order confirmation | `/checkout/confirmation/{orderId}` | US04 | Show the placed order | `GET /api/v1/orders/{orderId}` | Buyer who owns the order | **Continue shopping** | `/products` | #80 (PR #94) |
| Seller product creation | `/seller/products/new` | US06 | Create a product listing | `GET /api/v1/auth/me`, `POST /api/v1/seller/products` | Seller | **Create listing** | **View product** (`/products/{code}`) | #81 (PR #95) |
| Seller order management | `/seller/orders` | US08 | Process the seller's own sub-orders | `GET /api/v1/seller/orders`, `PATCH /api/v1/seller/orders/{subOrderId}/status` | Seller | Status buttons on each order | The refreshed list | #82 (PR #96) |
| Login | `/login` | All | Sign in as a buyer or seller | `POST /api/v1/auth/login` | Guest | **Log in** | `return_to` destination, else `/products` | #75 (PR #89) |

### Navigation flows

**Buyer flow** (checked end to end in a browser, see the evidence):

```text
/  --307-->  /products --search/card--> /products/{productCode}
                                              |  Add to Cart
                          guest: /login?return_to=/products/{code}?quantity=N
                                              |  (quantity restored, Add to Cart again)
                                              v
                                            /cart --Checkout--> /checkout
                                                                  |  Confirm order
                                                                  v
                                            /checkout/confirmation/{orderId}
                                                                  |  Continue shopping
                                                                  v
                                                              /products
```

**Seller flow:**

```text
/products --Create product--> /seller/products/new  (guest: /login?return_to=%2Fseller%2Fproducts%2Fnew)
                                     |  Create listing
                                     v
                              success panel --View product--> /products/{code}

/seller/orders  (opened by URL; no navigation link yet, gap UI-G6)
      |  Start processing / Cancel / Mark shipped / Mark completed
      v
refreshed list with the new status
```

## 2. Screen wireframes

Prices use the `vi-VN` currency format, for example `180.000 ₫`. Every screen
renders names, descriptions and server messages with `textContent`.

### 2.1 Product catalog — `/products`

```text
┌─────────────────────────────────────────────────────────────┐
│             Products  Cart  Create product  Log in|Log out   │
│ Products                                                    │
│ Search products [Search by product name          ] [Search] │
├─────────────────────────────────────────────────────────────┤
│ ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐     │
│ │ [image]   │ │ [image]   │ │ [image]   │ │ [image]   │     │
│ │ Name      │ │ Name      │ │ Name      │ │ Name      │     │
│ │ 180.000 ₫ │ │ 650.000 ₫ │ │ 90.000 ₫  │ │ 280.000 ₫ │     │
│ │ In Stock  │ │Only 3 left│ │ In Stock  │ │ In Stock  │     │
│ └───────────┘ └───────────┘ └───────────┘ └───────────┘     │
│              [Previous]  Page 1 of 3  [Next]                │
└─────────────────────────────────────────────────────────────┘
```

- **Purpose:** Browse active products that have available stock
  (`stock_quantity > reserved_stock`, BR1), 20 per page, ordered by id, with a
  case-insensitive name search.
- **Endpoint:** `GET /api/v1/products?page={page}&limit=20[&search=...]`.
- **Access:** Guest.
- **Primary CTA:** Select a product card (the whole card is a link).
- **Next step:** `/products/{productCode}`; **Create product** opens the seller form.

| State | What the user sees |
|---|---|
| Loading | Eight grey card skeletons; status "Loading products…" for screen readers |
| Data | Cards with image, name, price and a stock badge ("In Stock", or "Only N left" for 1-5 available); pagination "Page N of M" |
| Empty | "No products available at the moment." (also when a search finds nothing) |
| Error | "Something went wrong. Please try again later." and **Retry** |

A missing or broken image falls back to `/static/product-placeholder.svg` once.

**Changed from the initial wireframe:** no Filters control; out-of-stock products are
hidden instead of listed with a badge (Sprint 3 refinement, #74); the header links are
Products, Cart, Create product and Log in/Log out.

### 2.2 Product detail — `/products/{productCode}`

```text
┌─────────────────────────────────────────────────────────────┐
│                       Products  Cart  Log in|Log out        │
│ ← Back to products                                          │
│ ┌───────────────────┐  Wireless Mouse                       │
│ │      [image]      │  180.000 ₫                            │
│ │                   │  Wireless mouse for study and office  │
│ │                   │  In Stock (10 available)              │
│ └───────────────────┘  Quantity [ 1 ]  [Add to Cart]        │
└─────────────────────────────────────────────────────────────┘
```

- **Purpose:** Show the information needed to buy one product.
- **Endpoints:** `GET /api/v1/products/{productCode}`; **Add to Cart** calls
  `POST /api/v1/cart/items`.
- **Access:** Guest; adding to the cart needs a buyer token.
- **Primary CTA:** **Add to Cart**.
- **Next step:** On success, `/cart`. A guest is sent to
  `/login?return_to=/products/{code}?quantity=N`; after login the page restores
  the quantity and the buyer selects **Add to Cart** again.

| State | What the user sees |
|---|---|
| Loading | "Loading product…" |
| Data | Name, price, description ("No description available." when empty), image, "In Stock (N available)" |
| Out of stock | "Out of stock"; **Add to Cart** disabled |
| Not found | "Product not found." and **Back to catalogue** (no Retry) |
| Error | "Something went wrong. Please try again later.", **Back to catalogue** and **Retry** |
| Add failed | The server message under the button, for example "Cannot add more than 10 items (available stock limit)" or "A buyer account is required." |

**Changed from the initial wireframe:** the route uses the public code (`P-100`);
the quantity is a number field instead of −/+ buttons; the out-of-stock text is
"Out of stock".

### 2.3 Cart — `/cart`

```text
┌─────────────────────────────────────────────────────────────┐
│                                  Products  Cart  [Log out]  │
│ Your cart                                                   │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ [img] Demo cart item           [−] [ 2 ] [+]  200.000 ₫ │ │
│ │       100.000 ₫ each                          [Remove]  │ │
│ │       P-DEMO-CART · Available: 12                       │ │
│ └─────────────────────────────────────────────────────────┘ │
│ Total: 200.000 ₫                        Continue shopping   │
│ No shipping fee is added at checkout.        [Checkout]     │
└─────────────────────────────────────────────────────────────┘
```

- **Purpose:** Review cart lines and adjust quantities before checkout (BR2).
- **Endpoints:** `GET /api/v1/cart`; `PATCH` and `DELETE /api/v1/cart/items/{productCode}`.
  Every call returns the whole cart, so the page always shows the server's totals.
- **Access:** Buyer. Without a token, or after a `401`, the page goes to
  `/login?return_to=%2Fcart`.
- **Primary CTA:** **Checkout**.
- **Next step:** `/checkout`. Checkout is disabled while any line is flagged.

#### Required cart states

| State | What the user sees | User action |
|---|---|---|
| Loading | Three grey line skeletons; status "Loading your cart…" | Wait |
| Empty | "Your cart is empty.", "Total: 0 ₫" and **Continue shopping** | Return to `/products` |
| Data | Lines with image, name, unit price, code, available stock, −/quantity/+, line total and **Remove**; cart total; **Checkout** | Change quantities, remove lines, check out |
| Error | "Unable to load your cart. Please try again." and **Retry** | Retry the request |

Line-level feedback inside the data state:

- A quantity above available stock keeps the previous quantity and shows the server
  message beside the line: "Cannot add more than 12 items (available stock limit)".
- A typed quantity that is not a whole number of at least 1: "Enter a whole number of
  at least 1."
- Another failed change: "We could not update your cart. Please try again."
- A line whose product was withdrawn or ran out is kept and flagged with "This product
  is no longer available." or "This product is out of stock."; the summary says
  "Update or remove the highlighted items before checkout." and **Checkout** is
  disabled.
- A seller token gets "A buyer account is required." without **Retry**.

**Changed from the initial wireframe:** the shipping line became "No shipping fee is
added at checkout." (#85), matching checkout, which charges the cart total only.

### 2.4 Checkout — `/checkout`

```text
┌─────────────────────────────────────────────────────────────┐
│ Mini Marketplace  Cart                                      │
│ Checkout                                                    │
│ Enter delivery information.                                 │
│ Demo cart item × 2: 200.000 ₫                               │
│ Total: 200.000 ₫                                            │
│ Recipient name   [                                      ]   │
│ Delivery address [                                      ]   │
│ Phone number     [                                      ]   │
│ [Confirm order]                                             │
│ Back to cart · Continue shopping                            │
└─────────────────────────────────────────────────────────────┘
```

- **Purpose:** Collect delivery details and place one atomic order (BR3, BR8).
- **Endpoints:** `GET /api/v1/auth/me` and `GET /api/v1/cart` for the summary;
  `POST /api/v1/orders` with an `Idempotency-Key` header.
- **Access:** Buyer; a guest goes to `/login?return_to=%2Fcheckout`.
- **Primary CTA:** **Confirm order**.
- **Next step:** `/checkout/confirmation/{orderId}`.
- **Input rules:** recipient name 1-100 characters, address 1-1000 characters, phone
  7-20 characters with 7-15 digits (spaces, `+`, `-`, parentheses allowed); text is
  trimmed. No shipping fee is added.

| State | What the user sees |
|---|---|
| Loading | "Loading your cart..." |
| Data | The summary lines, total and the delivery form; "Enter delivery information." |
| Empty | "Your cart is empty."; the form stays hidden |
| Blocked | "Update unavailable items in your cart first."; the form stays hidden |
| Submitting | Fields and button disabled; "Placing your order..." |
| Field error | "Please enter recipient name.", "Please enter delivery address." or "Phone number must contain 7 to 15 digits."; values kept |
| Server error | The server message, for example "Item Demo cart item has insufficient stock or changed."; status "Order was not confirmed. Your delivery information is preserved." |
| Timeout | Same status and **Retry**, which resends the same key and body so at most one order exists |
| Account changed | "Your account has changed. Reload checkout before confirming." and **Reload checkout** |

Before submitting, the page saves the request key and body in sessionStorage scoped
to the account; reloading restores a pending request. A definite client error
(`4xx` except `401`) unlocks the form.

**Changed from the initial wireframe:** no "Step 2 of 2" header and no shipping fee;
the stock-race message is the server's "Item {name} has insufficient stock or
changed."

### 2.5 Seller product creation — `/seller/products/new`

```text
┌─────────────────────────────────────────────────────────────┐
│                               Products  Create product      │
│ Seller center › New product                                 │
│ New product                                                 │
│ Signed in as Demo Seller.                                   │
│ ┌ Please correct the highlighted fields. ─────────────────┐ │
│ │ • Price must be greater than 0 ₫.                       │ │
│ └─────────────────────────────────────────────────────────┘ │
│ Product name   [                                        ]   │
│ Description    [                                        ]   │
│ Price (₫)      [          ]   Stock quantity [          ]   │
│ Image URL      [https://example.com/product.jpg         ]   │
│ New listings are created active. A listing with stock 0     │
│ stays out of the catalog until it has stock.                │
│                                    [Cancel] [Create listing]│
└─────────────────────────────────────────────────────────────┘
```

- **Purpose:** Let a seller create a listing with a valid price and stock (BR5, BR9).
- **Endpoints:** `GET /api/v1/auth/me`; `POST /api/v1/seller/products` (JSON).
- **Access:** Seller. A guest goes to `/login?return_to=%2Fseller%2Fproducts%2Fnew`;
  a buyer sees "Only seller accounts can create product listings." with **Back to
  products** and **Log in as a seller**.
- **Primary CTA:** **Create listing**.
- **Next step:** A success panel with the name, "Product code: P-…", **View product**
  (`/products/{code}`), **Continue browsing** and **Create another product**.
- **Input rules:** name 1-200 characters on one line, description 1-3000 characters,
  both with at least one visible character; whole-number price 1 to 1.000.000.000 ₫;
  stock 0 to 1.000.000; absolute http(s) image URL up to 2048 characters. The server
  sets the seller, code, status (`is_active = true`) and version.

| State | What the user sees |
|---|---|
| Checking | "Checking your account…"; the form is hidden |
| Data | The form and "Signed in as {name}." |
| Submitting | Every control disabled; "Creating listing..." |
| Field error | A message under each field (for example "Price must be greater than 0 ₫.") and the summary "Please correct the highlighted fields."; focus on the first invalid field; values kept |
| Server error | Summary "The listing was not created." with the server message; values kept |
| Timeout | Summary "The listing was not confirmed." with a warning not to resubmit blindly; never resent automatically |
| Success | The success panel; stock 0 adds "Stock is 0: the product page shows Out of stock, and the listing stays out of the catalog until it has stock." |
| Account changed | "Your account changed in another tab. Reload this page before creating a product." and **Reload page** |

**Changed from the initial wireframe:** "Upload image" became **Image URL** and the
"Active listing" checkbox became a fixed note (#81); a broken image URL keeps the
listing and shows the placeholder.

### 2.6 Seller order management — `/seller/orders`

```text
┌─────────────────────────────────────────────────────────────┐
│ Products [Log out]                                          │
│ Seller orders                                               │
│ Status [All v]  From [mm/dd/yyyy]  To [mm/dd/yyyy]  [Filter]│
│ 3 seller orders found.                                      │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Order #5 (parent #5)                            PENDING │ │
│ │ Customer: Nguyen Minh Anh                               │ │
│ │ • Demo cart item × 2 (200.000 ₫)                        │ │
│ │ [Start processing] [Cancel]                             │ │
│ └─────────────────────────────────────────────────────────┘ │
│              [Previous]  Page 1 of 1  [Next]                │
└─────────────────────────────────────────────────────────────┘
```

- **Purpose:** Show only the authenticated seller's sub-orders and move them through
  `PENDING → PROCESSING → SHIPPED → COMPLETED`, or `PENDING → CANCELLED` (BR6).
- **Endpoints:** `GET /api/v1/seller/orders?status=&from=&to=&page=&limit=20`;
  `PATCH /api/v1/seller/orders/{subOrderId}/status`.
- **Access:** Seller.
- **Primary CTA:** The button for the next allowed status: **Start processing** and
  **Cancel** (PENDING), **Mark shipped** (PROCESSING), **Mark completed** (SHIPPED);
  none for COMPLETED or CANCELLED. **Cancel** first asks "Cancel this order and
  restore stock?".
- **Next step:** The list reloads with the new status. Cancelling restores stock once;
  every change writes an `order_history` row.

| State | What the user sees |
|---|---|
| Loading | "Loading orders…" |
| Data | One card per sub-order: "Order #{id} (parent #{orderId})", status, customer, items with totals, status buttons; "{n} seller orders found." |
| Empty | "No seller orders found." |
| Error | "Unable to load seller orders." and **Retry**; the status line shows the server message, for example "A seller account is required." for a buyer |

**Changed from the initial wireframe:** cards instead of a table on every screen
size; one **Filter** button instead of a date-range picker; no **Clear filters**.
Known gaps UI-G3 to UI-G6 in section 4.3 apply to this screen.

### 2.7 Login — `/login`

```text
┌──────────────────────────────────────────────┐
│                                   Products   │
│ Log in                                        │
│ Email     [                              ]    │
│ Password  [                              ]    │
│ [Log in]                                      │
│ Email or password is incorrect.               │
└──────────────────────────────────────────────┘
```

- **Purpose:** Authenticate buyers and sellers before protected actions.
- **Endpoint:** `POST /api/v1/auth/login`; the token is kept in `localStorage`.
- **Access:** Guest.
- **Primary CTA:** **Log in**.
- **Next step:** The `return_to` path when it is a local path, otherwise `/products`.
- **Error state:** "Email or password is incorrect." without saying which one was
  wrong; "Unable to log in." when the server gives no message.

**Changed from the initial wireframe:** no "Forgot password?" or account creation
(not in the P0 scope); no loading text (gap UI-G7); sellers also land on `/products`
instead of a seller workspace.

### 2.8 Order confirmation — `/checkout/confirmation/{orderId}`

```text
┌─────────────────────────────────────────────────────────────┐
│ Mini Marketplace  Cart                                      │
│ Order confirmation                                          │
│ Order placed successfully.                                  │
│ Order #5 · PENDING                                          │
│ Total: 200.000 ₫                                            │
│ Nguyen Minh Anh · 12 Le Loi, District 1 · 0912345678        │
│ Product #46 × 2 · 100000 VND each                           │
│ Continue shopping                                           │
└─────────────────────────────────────────────────────────────┘
```

- **Purpose:** Confirm the order and show its reference, status, total and delivery.
- **Endpoint:** `GET /api/v1/orders/{orderId}` (read only; never places an order).
- **Access:** The buyer who owns the order; any other buyer gets "Order not found."
  (BR4).
- **Primary CTA:** **Continue shopping**.

| State | What the user sees |
|---|---|
| Loading | "Loading confirmation..." |
| Data | "Order placed successfully." and the receipt lines |
| Not found / error | "Confirmation unavailable.", the server message (for example "Order not found.") and **Retry** |

**Changed from the initial wireframe:** no **View order details** (buyer order history
is US05, P1, not built); item lines show the product id and an unformatted unit price
(gap UI-G2).

## 3. Shared interaction and responsive rules

### 3.1 Rules

- Every action is a native link or button, so it is keyboard reachable with a visible
  focus outline.
- Validation errors appear beside the related field on the seller product form, with
  `aria-invalid`, `aria-describedby` and a `role="alert"` summary. Checkout and cart
  show their single message in a `role="alert"` or `role="status"` region.
- Buttons are disabled while their request is pending (cart lines, checkout, seller
  product form) to prevent duplicate submissions.
- Prices use the `vi-VN` currency format, for example `180.000 ₫` (except UI-G2).
- Pages that call the API show loading, empty or data, and error states; error states
  offer **Retry** when retrying can help.
- Protected buyer pages and the seller product form return to the intended page after
  login with `return_to` (except `/seller/orders`, UI-G3).
- On mobile (390 px wide) the catalog shows two cards per row, cart lines stack their
  controls, checkout is one column and seller orders are cards; no page scrolls
  sideways.
- API errors use `{"error": {"code", "message"}}`; the pages show `message`, never
  SQL or stack traces.

### 3.2 Error cases: API code, business rule and UI message

Each row is a case a user can meet. "UI message" is the exact text on the screen;
`{...}` marks a value filled in at run time. Business rules are those of
[traceability.md](traceability.md#business-rules).

| Case | Screen | Trigger | HTTP / error code | Rule | UI message | Recovery | Automated check |
|---|---|---|---|---|---|---|---|
| UI-E01 | Catalog | The catalog query fails | `500 ERR_DATABASE_FAILURE` | BR1 | `Something went wrong. Please try again later.` | **Retry** | `test_list_products_database_failure_returns_500` |
| UI-E02 | Product detail | Unknown or inactive product code | `404 ERR_PRODUCT_NOT_FOUND` | BR1 | `Product not found.` | **Back to catalogue** | `test_product_detail_hides_inactive_and_unknown_products` |
| UI-E03 | Product detail | No available stock | `200`, `stock_status: out_of_stock` | BR1, BR2 | `Out of stock` | Add to Cart disabled | `test_out_of_stock_product_remains_visible_but_unavailable` |
| UI-E04 | Cart | Quantity above available stock | `409 ERR_STOCK_EXCEEDED` | BR2 | `Cannot add more than {available} items (available stock limit)` | Previous quantity kept | `test_quantity_above_stock_is_refused_and_the_previous_one_kept` |
| UI-E05 | Cart | Typed quantity is not a whole number of at least 1 | none (checked in the page; the API answers `400 ERR_INVALID_QUANTITY` or `422 ERR_VALIDATION`) | BR2 | `Enter a whole number of at least 1.` | Previous quantity restored | `test_add_refuses_an_invalid_quantity` |
| UI-E06 | Cart | A seller opens the cart | `403 ERR_BUYER_REQUIRED` | — | `A buyer account is required.` | Log in as a buyer | `test_seller_has_no_cart` |
| UI-E07 | Cart | The cart cannot be loaded | `500` or network error | — | `Unable to load your cart. Please try again.` | **Retry** | `test_database_failure_is_a_500_without_sql_details` |
| UI-E08 | Checkout | Stock changed after the cart was filled | `409 ERR_STOCK_EXCEEDED` | BR8 | `Item {name} has insufficient stock or changed.` | Form values kept; update the cart | `test_stale_product_version_aborts_checkout` |
| UI-E09 | Checkout | Invalid phone number | none (checked in the page; the API answers `422 ERR_VALIDATION`) | — | `Phone number must contain 7 to 15 digits.` | Correct the field | `test_api_validation_does_not_write` |
| UI-E10 | Checkout | Empty cart | `400 ERR_EMPTY_CART` | — | `Your cart is empty.` | **Continue shopping** | `test_auth_empty_cart_key_and_pages` |
| UI-E11 | Checkout | Same Idempotency-Key with a different body | `409 ERR_IDEMPOTENCY_CONFLICT` | — | `Key was used for another request.` | Start a new checkout | `test_replay_before_empty_cart_check_and_payload_conflict` |
| UI-E12 | Order confirmation | Another buyer's order id | `404 ERR_ORDER_NOT_FOUND` | BR4 | `Order not found.` | **Continue shopping** | `test_api_create_replay_and_ownership` |
| UI-E13 | Seller product form | Price 0 or negative | `422 ERR_VALIDATION`, `error.fields.price` | BR9 | `Price must be greater than 0 ₫.` | Values kept; fix the field | `test_invalid_field_is_reported_beside_that_field_and_nothing_is_written` |
| UI-E14 | Seller product form | A buyer opens the form or calls the API | `403 ERR_SELLER_REQUIRED` | BR5 | `Only seller accounts can create product listings.` | **Log in as a seller** | `test_guests_buyers_and_invalid_tokens_cannot_create` |
| UI-E15 | Seller product form | The request names a seller | `422 ERR_VALIDATION`, `error.fields._form` | BR5 | `{field} is set by the server and cannot be sent.` | None needed; the form never sends it | `test_the_owner_always_comes_from_the_token_never_the_body` |
| UI-E16 | Seller orders | A transition that is not allowed | `400 ERR_INVALID_TRANSITION` | BR6 | `Transition from {from} to {to} is not allowed.` | Only allowed buttons are shown | `test_invalid_transition_returns_business_error` |
| UI-E17 | Seller orders | Another seller's sub-order | `403 ERR_RESOURCE_OWNER` | BR6 | `You do not own this seller order.` | **Retry** reloads the own list | `test_other_seller_cannot_update_owned_order` |
| UI-E18 | Seller orders | A buyer opens the page | `403 ERR_SELLER_REQUIRED` | BR6 | `A seller account is required.` | Log in as a seller | `test_buyers_and_guests_cannot_use_seller_orders` |
| UI-E19 | Login | Wrong email or password | `401 ERR_INVALID_CREDENTIALS` | — | `Email or password is incorrect.` | Try again | `test_invalid_credentials_use_common_error_shape` |
| UI-E20 | Any protected page | Expired or invalid token | `401 ERR_AUTH_REQUIRED` / `ERR_INVALID_TOKEN` | BR3 | `The access token is invalid or expired.` | Pages other than `/seller/orders` go to `/login` with `return_to` | `test_missing_and_expired_tokens_are_rejected` |

The complete list of API error codes, including those no screen can trigger, is in
[design.md section 3.4](design.md#34-error-handling).

## 4. Review checklist and implementation handoff

### 4.1 Wireframe review checklist

- [x] Wireframes for the six P0 screens, login and confirmation were reviewed before
  implementation: PR #88 (#76), changes requested and then approved by @minhnm162,
  approved by @MinhQuangQu.
- [x] Engineering confirmed each endpoint and state: every screen above runs on
  `main` and its states were checked in a browser on 2026-10-18
  ([evidence](evidence/milestone3.md)).
- [x] Keyboard order, focus and labels were checked on the seller product form
  (#81) and the main buyer pages; screen-reader testing has not been done.
- [ ] Product owner, buyer and seller review of the running screens: planned in #83
  (heuristic reviews and user sessions), not yet recorded.

### 4.2 Implementation status

| Screen | Story / issue | PR | Automated tests | Browser evidence |
|---|---|---|---|---|
| `/` | US01 / #83 | #97 (open) | `test_browser_root_enters_catalog_without_changing_json_status` | M3-01 |
| `/products` | US01 / #77 | #90 | `tests/test_products.py`, `tests/test_products_page.py` | M3-02 to M3-05 |
| `/products/{productCode}` | US02 / #78 | #91 | `tests/test_product_detail.py` | M3-06 to M3-08 |
| `/cart` | US03 / #79 | #92 | `tests/test_cart_api.py`, `tests/test_cart_service.py`, `tests/test_cart_page.py` | M3-11 to M3-16 |
| `/checkout` | US04 / #80 | #94 | `tests/test_checkout.py`, `tests/checkout_ui.mjs` | M3-17 to M3-18 |
| `/checkout/confirmation/{orderId}` | US04 / #80 | #94 | `tests/test_checkout.py` | M3-19 |
| `/seller/products/new` | US06 / #81 | #95 | `tests/test_seller_products.py`, `tests/seller_products_ui.mjs` | M3-20 to M3-21 |
| `/seller/orders` | US08 / #82 | #96 | `tests/test_seller_orders.py` | M3-22 to M3-25 |
| `/login` | Auth / #75 | #89 | `tests/test_auth.py` | M3-09 to M3-10 |
| End to end | #83 | #97 (open) | `tests/test_p0_flows.py` | Buyer and seller flows above |

### 4.3 Known gaps and follow-ups

Found while finalizing this document; none blocks a P0 acceptance criterion. Each is
a candidate for the Sprint 3 wrap-up (#86) or Sprint 4.

| Gap | Screen | What happens | Suggested change | Area owner |
|---|---|---|---|---|
| UI-G1 | All | An unknown `/api/v1/...` path answers Starlette's `{"detail": "Not Found"}`, not the error envelope | Register a handler for Starlette's `HTTPException` | @leducminh290506-eng (#75) |
| UI-G2 | Confirmation | Item lines show "Product #46" and "100000 VND" instead of the name and `100.000 ₫` | Return the product name in `OrderLine` and format the price | @minhnm162 (#80) |
| UI-G3 | Seller orders | A guest sees "The access token is invalid or expired." instead of going to login | Redirect to `/login?return_to=%2Fseller%2Forders` on a missing token or `401` | @leducminh290506-eng (#82) |
| UI-G4 | Seller orders | A network failure shows the browser text "Failed to fetch" | Show "Unable to load seller orders." only | @leducminh290506-eng (#82) |
| UI-G5 | Seller orders | A failed status change replaces the list with the error state | Keep the last list and show the message beside the order | @leducminh290506-eng (#82) |
| UI-G6 | Seller orders | No page links to `/seller/orders` | Add a seller navigation link | @leducminh290506-eng (#82) |
| UI-G7 | Login | No loading text and the button stays enabled while signing in | Disable the button and show "Signing in..." | @leducminh290506-eng (#75) |
