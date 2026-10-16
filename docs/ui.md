# P0 Wireframes and Initial UI Documentation

This document defines the initial UI contract for the six P0 Milestone 1
screens, plus the shared login and order-confirmation screens. These are
low-fidelity wireframes for review before implementation. They describe
layout, states, permissions, API dependencies, and the next user action;
visual styling and component implementation may evolve after review.

## 1. Screen inventory and navigation

| Screen | Route | Purpose | Endpoint(s) | Access | Primary CTA | Next step |
|---|---|---|---|---|---|---|
| Product catalog | `/products` | Discover active marketplace products | `GET /api/v1/products?page=1&limit=20` | Guest | View details | Product detail |
| Product detail | `/products/:productCode` | Review one product before buying | `GET /api/v1/products/{productCode}` | Guest | Add to cart | Cart, or login then return to detail |
| Cart | `/cart` | Review items and adjust quantities | `GET /api/v1/cart`, `POST/PATCH/DELETE /api/v1/cart/items` | Authenticated buyer | Proceed to checkout | Checkout |
| Checkout | `/checkout` | Enter delivery information and place order | `POST /api/v1/orders` | Authenticated buyer | Confirm order | Confirmation |
| Seller product creation | `/seller/products/new` | Create a product listing | `POST /api/v1/seller/products` | Authenticated seller | Create listing | Created product |
| Seller order management | `/seller/orders` | Process seller-owned order items | `GET/PATCH /api/v1/seller/orders` | Authenticated seller | Update status | Next order or dashboard |
| Login | `/login` | Authenticate a buyer or seller | `POST /api/v1/auth/login` | Guest | Sign in | Return to intended screen |
| Order confirmation | `/checkout/confirmation/{orderId}` | Confirm successful order creation | `GET /api/v1/orders/{orderId}` | Authenticated buyer | Continue shopping / View order | Catalog or order history |

### Navigation flows

**Buyer flow**

```text
/login (only when authentication is required)
       |
       v
/products --> /products/:productCode --> /cart --> /checkout
                                                   |
                                                   v
                                      /checkout/confirmation/{orderId}
```

**Seller flow**

```text
/login --> /seller/products/new --> created product
                                      |
                                      v
                              /seller/orders
                                      |
                                      v
                              update sub-order status
```

## 2. Screen wireframes

### 2.1 Product catalog — `/products`

```text
┌─────────────────────────────────────────────────────────────┐
│ Mini Marketplace                         [Cart] [Account]   │
├─────────────────────────────────────────────────────────────┤
│ Products                                      [Search]      │
│ Browse active products                         [Filters]     │
├─────────────────────────────────────────────────────────────┤
│ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐            │
│ │ [image]     │ │ [image]     │ │ [image]     │            │
│ │ Product name│ │ Product name│ │ Product name│            │
│ │ 180.000 ₫   │ │ 95.000 ₫    │ │ 60.000 ₫    │            │
│ │ In stock    │ │ Only 2 left │ │ [View]      │            │
│ └─────────────┘ └─────────────┘ └─────────────┘            │
│                                                             │
│                 [Previous] 1 2 [Next]                       │
└─────────────────────────────────────────────────────────────┘
```

- **Purpose:** Browse active products with image, name, price, and stock
  status.
- **Endpoint:** `GET /api/v1/products?page={page}&limit=20`.
- **Access:** Guest.
- **Primary CTA:** Select a product card or its **View details** action.
- **Next step:** Navigate to `/products/:productCode`; the cart icon goes to
  `/cart`. The catalog itself does not add items directly.
- **Data state:** Product grid with 20 items per page and pagination.
- **Loading state:** Show product-card skeletons while the request is pending.
- **Empty state:** Hide the grid and show exactly
  `No products available at the moment.` with a link to continue browsing or
  return home.
- **Error state:** Show `Something went wrong. Please try again later.` and a
  **Retry** action.

### 2.2 Product detail — `/products/:productCode`

```text
┌─────────────────────────────────────────────────────────────┐
│ ← Back to products                              [Cart]      │
├─────────────────────────────────────────────────────────────┤
│ ┌───────────────────┐  Winter Children Jacket              │
│ │                   │  180.000 ₫                            │
│ │      [image]      │  Warm jacket for children.            │
│ │                   │  Stock: In Stock (10 remaining)       │
│ └───────────────────┘  Quantity [-] 1 [+]                  │
│                          [Add to cart]                       │
└─────────────────────────────────────────────────────────────┘
```

- **Purpose:** Show the complete product information needed for a purchase
  decision.
- **Endpoint:** `GET /api/v1/products/{productCode}`.
- **Access:** Guest.
- **Primary CTA:** **Add to cart**.
- **Next step:** For an authenticated buyer, add the item and go to `/cart`;
  preserve the product code and selected quantity. For a guest, redirect to
  `/login` with the requested product detail route and selected quantity as
  the intended destination. After successful login, return to
  `/products/:productCode`, restore the selected quantity, and require the
  buyer to confirm **Add to cart** again before navigating to `/cart`.
- **Data state:** Show full name, formatted price, description, image, and
  stock status.
- **Loading state:** Show image and text skeletons.
- **Empty/not-found state:** Show `Product not found` and a **Back to
  products** action.
- **Error state:** Show a retry action without losing the requested product
  code.
- **Out-of-stock state:** Show `Out of Stock (0 remaining)` and disable
  **Add to cart**.
- **Authentication state:** Guests may view the detail page, but selecting
  **Add to cart** redirects to `/login`; the login flow must preserve the
  product detail route and selected quantity as the return context.

### 2.3 Cart — `/cart`

```text
┌─────────────────────────────────────────────────────────────┐
│ Your cart                                      [Products]   │
├─────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ [image] Product name    180.000 ₫  [-] 3 [+]  540.000 ₫│ │
│ │         Available: 10                         [Remove]  │ │
│ └─────────────────────────────────────────────────────────┘ │
│ Subtotal: 540.000 ₫     Shipping: calculated at checkout    │
│ Total: 540.000 ₫                         [Checkout]         │
└─────────────────────────────────────────────────────────────┘
```

- **Purpose:** Review cart lines and manage quantities before checkout.
- **Endpoints:** `GET /api/v1/cart`; `POST`, `PATCH`, and `DELETE
  /api/v1/cart/items`.
- **Access:** Authenticated buyer; unauthenticated visitors are sent to
  `/login` and returned to `/cart` after login.
- **Primary CTA:** **Checkout**.
- **Next step:** Navigate to `/checkout` only when the cart has valid items.
- **Data state:** Show each item, public `product_code`, price, quantity,
  line subtotal, cart total, and available stock.
- **Quantity error:** Keep the previous quantity and show
  `Cannot add more than {stock} items (available stock limit)`.

#### Required cart states

| State | Wireframe/content | User action |
|---|---|---|
| Loading | Cart-line skeletons and a disabled checkout button | Wait for cart data |
| Empty | `Your cart is empty.`; total `0 ₫`; **Continue shopping** button | Return to `/products` |
| Data | Cart lines, quantity controls, remove actions, subtotal, and **Checkout** | Adjust items or continue |
| Error | `Unable to load your cart. Please try again.` and **Retry** | Retry the cart request |

### 2.4 Checkout — `/checkout`

```text
┌─────────────────────────────────────────────────────────────┐
│ Checkout                                      Step 2 of 2   │
├───────────────────────────────┬─────────────────────────────┤
│ Delivery information           │ Order summary               │
│ Recipient name [             ] │ Product x 3   540.000 ₫     │
│ Address       [             ] │ Shipping       20.000 ₫     │
│ Phone         [             ] │ Total         560.000 ₫     │
│                               │                             │
│ [Back to cart] [Confirm order]│                             │
└───────────────────────────────┴─────────────────────────────┘
```

- **Purpose:** Validate delivery details, recheck stock, and place the order.
- **Endpoint:** `POST /api/v1/orders`.
- **Access:** Authenticated buyer.
- **Primary CTA:** **Confirm order**.
- **Next step:** On success, navigate to
  `/checkout/confirmation/{orderId}`.
- **Data state:** Show cart items, quantities, prices, delivery form, fees,
  and final total.
- **Loading state:** Disable form controls and show `Placing your order...`.
- **Empty state:** If the cart is empty, show `Your cart is empty.` and a
  **Return to products** action; do not submit an order.
- **Error state:** Preserve form values and identify the invalid field or
  unavailable product. For a stock race, show
  `Item {name} is out of stock. Please update your cart.`

### 2.5 Seller product creation — `/seller/products/new`

```text
┌─────────────────────────────────────────────────────────────┐
│ Seller center > New product                                 │
├─────────────────────────────────────────────────────────────┤
│ Product name      [                                      ]  │
│ Description       [                                      ]  │
│ Price             [                  ] ₫                    │
│ Stock quantity    [                  ]                      │
│ Image URL         [https://...                           ]  │
│ New listings are created active.                            │
│                                                             │
│ [Cancel]                              [Create listing]       │
└─────────────────────────────────────────────────────────────┘
```

- **Purpose:** Let a seller create a product listing with valid price and
  stock.
- **Endpoint:** `POST /api/v1/seller/products`.
- **Access:** Authenticated seller only.
- **Primary CTA:** **Create listing**.
- **Next step:** Show the newly created product using its returned
  `productCode` and link to `/products/:productCode`. A seller product-list
  route is not part of this UI contract; `/seller/orders` remains a separate
  navigation destination for managing incoming orders.
- **Data state:** Form fields for name, description, price, stock and image
  URL. A new listing is always created active (#81); stock 0 shows it as out of
  stock instead of hiding it.
- **Loading state:** Disable submission and show `Creating listing...`.
- **Empty state:** Not applicable to the form; blank fields show required-field
  guidance before submission.
- **Error state:** Keep entered values and show field-level errors, including
  `Price must be greater than 0 ₫`.
- **Authorization state:** Non-sellers receive a forbidden message and a link
  to the appropriate account page.

### 2.6 Seller order management — `/seller/orders`

```text
┌─────────────────────────────────────────────────────────────┐
│ Seller orders                    [Status v] [Date range v]  │
├───────┬──────────────┬──────────┬──────────┬───────────────┤
│ Order │ Product      │ Quantity │ Total    │ Status        │
├───────┼──────────────┼──────────┼──────────┼───────────────┤
│ 10042 │ Jacket       │ 3        │ 540.000₫│ PENDING [v]   │
│ 10043 │ Keyboard     │ 1        │ 180.000₫│ PROCESSING[v] │
└───────┴──────────────┴──────────┴──────────┴───────────────┘
│ [Previous] 1 2 [Next]                                      │
└─────────────────────────────────────────────────────────────┘
```

- **Purpose:** Show only the authenticated seller's order items and update
  fulfillment status.
- **Endpoints:** `GET /api/v1/seller/orders`; `PATCH
  /api/v1/seller/orders/{subOrderId}/status`.
- **Access:** Authenticated seller only.
- **Primary CTA:** **Update status** on a seller-owned sub-order.
- **Next step:** Refresh the row and show the transition in the status badge;
  invalid transitions remain unchanged and explain the reason.
- **Data state:** Paginated table with status/date filters.
- **Loading state:** Table-row skeletons.
- **Empty state:** `No orders match your filters.` with a **Clear filters**
  action.
- **Error state:** Show retry and do not replace the last successfully loaded
  table.
- **Authorization state:** A non-seller receives `403 Forbidden`; another
  seller's order item is never displayed.

### 2.7 Login — `/login`

```text
┌──────────────────────────────────────────────┐
│ Mini Marketplace                              │
│ Sign in                                       │
│ Email       [                             ]   │
│ Password    [                             ]   │
│ [Sign in]        Forgot password?             │
│                                              │
│ New here? Create an account                  │
└──────────────────────────────────────────────┘
```

- **Purpose:** Authenticate buyers and sellers before protected actions.
- **Endpoint:** `POST /api/v1/auth/login`.
- **Access:** Guest.
- **Primary CTA:** **Sign in**.
- **Next step:** Return to the originally requested route, or go to
  `/products` for buyers and the seller workspace for sellers.
- **Loading state:** Disable the button and show `Signing in...`.
- **Empty state:** Blank fields show required-field guidance.
- **Error state:** Show `Invalid email or password.` without revealing which
  credential was incorrect.

### 2.8 Order confirmation — `/checkout/confirmation/{orderId}`

```text
┌─────────────────────────────────────────────────────────────┐
│                    ✓ Order placed                           │
│              Thank you for your purchase                     │
│ Order number: #10042                                        │
│ Status: PENDING                                             │
│ Items: Winter Children Jacket x 3                           │
│ Total: 560.000 ₫                                            │
│ Delivery: Nguyễn Minh Anh, 123 Main Street                  │
│                                                             │
│ [Continue shopping]                 [View order details]     │
└─────────────────────────────────────────────────────────────┘
```

- **Purpose:** Confirm that checkout succeeded and provide the new order
  reference.
- **Endpoint:** `GET /api/v1/orders/{orderId}`.
- **Access:** Authenticated buyer who owns the order.
- **Primary CTA:** **Continue shopping** or **View order details**.
- **Next step:** Return to `/products` or the buyer's order history.
- **Loading state:** Confirmation skeleton while the order is retrieved.
- **Empty/not-found state:** `Order not found.` with a link to the catalog.
- **Error state:** Explain that confirmation could not be loaded and provide
  **Retry** without creating another order.

## 3. Shared interaction and responsive rules

- Every primary action has a visible focus state and is keyboard reachable.
- Validation errors appear beside the related field and in an `aria-live`
  summary for screen readers.
- Buttons are disabled while their request is pending to prevent duplicate
  submissions.
- Prices use the M1 display format, for example `180.000 ₫`.
- Product and seller lists preserve the last successful data while a refresh
  is loading.
- On mobile, the catalog becomes a two-column grid, cart lines stack their
  controls, checkout becomes one column, and seller order rows become cards.
- All protected routes preserve the intended destination through login.

## 4. Review checklist and implementation handoff

### Wireframe review checklist

- [ ] Product owner confirms the six P0 screens, login, and confirmation.
- [ ] Buyer confirms the catalog-to-checkout flow and cart quantity feedback.
- [ ] Seller confirms listing creation fields and order status transitions.
- [ ] Accessibility review confirms keyboard order, focus states, and labels.
- [ ] Engineering confirms each endpoint and response state is available.

### Implementation handoff

The wireframes are intentionally implementation-neutral. After review,
frontend tasks should turn each screen section into components and tests,
while preserving the documented endpoints, access rules, CTA labels, and
loading/empty/error/data behavior. This document should be updated if the
review changes the user flow or acceptance criteria.


### US04 runtime contract (#80)

The checkout summary uses GET /api/v1/cart. Final prices are calculated on the server;
shipping is zero (the fees in the earlier wireframe are illustrative, not charged).
Required input: recipient name 1-100 characters, address 1-1000 characters, phone
7-20 characters containing 7-15 digits; spaces, plus, hyphen and parentheses are
accepted. Whitespace is trimmed. Invalid fields are named in ERR_VALIDATION and
input is preserved; inventory errors identify the item and preserve the cart.

Before submitting, the page saves the request key and payload in account-scoped
sessionStorage. A timeout/server failure locks the fields; Retry reuses the same
key and payload. Reload restores that pending request. Success clears it and opens
/checkout/confirmation/{orderId}. A definite client error unlocks the form.
Confirmation Retry only uses GET; it never places a new order. Empty and unavailable
carts cannot submit. User-facing API text is rendered with textContent.


### US06 runtime contract (#81)

The wireframe's image upload became an **Image URL** field: the listing stores an
absolute http(s) URL and the server never downloads it. A URL that cannot be loaded
keeps the listing; the catalog card and product page show the existing placeholder.
The active checkbox became a fixed note: new listings are active, and a listing with
stock 0 is shown as Out of stock and left out of the catalog.

The page loads as a public shell and checks the account with `GET /api/v1/auth/me`
using the token it was loaded with. Guests go to
`/login?return_to=%2Fseller%2Fproducts%2Fnew`; buyers see a forbidden message with
**Back to products** and **Log in as a seller**. If the stored token changes (another
tab logs in or out), the page hides the form, sends nothing and asks for a reload.

Each field has a label, a hint where useful, and an error line linked with
`aria-describedby`. Invalid fields get `aria-invalid="true"`; the summary uses
`role="alert"`, and focus moves to the first invalid field. Client checks mirror the
server: required trimmed text, name up to 200 and description up to 3000 characters,
whole-number price 1 to 1.000.000.000 ₫ and stock 0 to 1.000.000, absolute http(s)
image URL. The server's `error.fields` are shown beside the matching inputs;
`_form`, 409, 500 and network errors appear in the summary only. While the request
is pending, every control is disabled and the status reads `Creating listing...`.
Entered values are kept after every failure. A timeout or network error is reported
as unconfirmed and never resent automatically. When the session expires during
submit, the values are kept in sessionStorage for the same seller and restored after
login. On success the form is replaced by the product name, its code, **View
product** (`/products/{code}`), **Continue browsing** and **Create another
product**. Names and server messages are rendered with `textContent`.

The catalog navigation links to the form as **Create product**.
