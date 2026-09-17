# US07 - Seller Updates Product Information and Stock Quantity

**Issue ID:** #19  
**Epic:** F4 Product Management  
**Priority:** P1 - Should have  
**Story Points:** 3  
**Related Routes:**  
- `/seller/products/:productId/edit` (Product Edit Workspace)  
- `/seller/products` (Seller Inventory Dashboard with quick-stock adjustment)

---

## 1. User Story

**As a seller,**  
**I want to update my product information and stock quantity,**  
**So that marketplace information remains accurate, prevents overselling, and reflects current store inventory.**

---

## 2. Detailed Acceptance Criteria (BDD Format)

### Scenario 1: Successful Update of Product Information (Happy Path)
- **Given** I am an authenticated seller and I own a product listing with ID `:productId`
- **When** I navigate to `/seller/products/:productId/edit`
- **And** I modify valid product fields (such as product name, description, category attributes, media gallery, dimensions, or price)
- **And** I click "Save Changes"
- **Then** the database commits the updated product details atomically
- **And** the changes become immediately visible to prospective buyers on the product catalog (`/products`) and product detail page (`/products/:id`)
- **And** the system displays a success notification: *"Product updated successfully."*

### Scenario 2: Stock Quantity Update & Availability Synchronization
- **Given** I own a product with current stock of 10
- **When** I update the stock quantity to a new valid integer value:
  - **Case 2A (Replenishment):** If I increase stock from `0` to `25`, the product status changes from *"Out of Stock"* to *"In Stock"*, and buyers can immediately add the product to their cart.
  - **Case 2B (Depletion):** If I reduce stock to `0`, the product automatically transitions to *"Out of Stock"*, the buyer detail page displays an *"Out of Stock"* badge, and both "Add to Cart" and "Buy Now" buttons are disabled.
  - **Case 2C (Partial adjustment):** If I adjust stock to `3` (below low-stock threshold <= 5), the buyer UI displays an urgency badge *"Only 3 left in stock"*.
- **Then** all stock modifications reflect in real time across the marketplace catalog.

### Scenario 3: Unauthorized Access & Product Ownership Violation (Security / IDOR)
- **Given** Product `P-999` belongs to Seller A
- **When** Seller B (authenticated under a different account) attempts to access `GET /seller/products/P-999/edit` or submits an update request `PUT /api/v1/seller/products/P-999`
- **Then** the system rejects the operation immediately
- **And** the API returns HTTP `403 Forbidden` with error code `ERR_PRODUCT_OWNERSHIP_DENIED`
- **And** no data from Product `P-999` is updated or leaked
- **And** the security event is logged in the marketplace audit log.

### Scenario 4: Invalid Price or Stock Input (Atomic Transaction Rollback)
- **Given** I own a product with an existing valid price of $45.00 and stock of 20
- **When** I attempt to submit an update containing:
  - A non-positive price (`price <= 0` or non-numeric string), OR
  - A negative stock quantity (`stock < 0`), OR
  - A floating-point stock value (`stock = 12.5`), OR
  - A stock quantity lower than the currently reserved buyer checkout quantity
- **Then** the API rejects the request with HTTP `422 Unprocessable Entity`
- **And** the database transaction is rolled back completely
- **And** all previous valid data (price $45.00, stock 20) remains 100% intact and unchanged
- **And** the UI preserves the seller's input, highlights the invalid fields in red, and displays clear actionable error messages without wiping the form.

### Scenario 5: Concurrency Conflict Handling (Optimistic Locking)
- **Given** a seller opens the edit screen for product `P-100` at version `v1`
- **When** a background buyer order decrements the stock or another store manager updates `P-100` (incrementing version to `v2`)
- **And** the seller submits their changes based on stale version `v1`
- **Then** the system detects the version mismatch
- **And** returns HTTP `409 Conflict` with error code `ERR_CONCURRENT_MODIFICATION`
- **And** prompts the seller to reload the latest product state before reapplying edits.

### Scenario 6: Marketplace Business Guardrails
- **Given** an active listing on the marketplace
- **When** the seller submits a price alteration exceeding ±80% of the existing price (e.g. from $100.00 down to $5.00 or up to $500.00)
- **Then** the interface displays an operational warning confirmation modal: *"Significant price change detected. Please verify your selling price to avoid unintended losses."*
- **And** requires explicit secondary confirmation before dispatching the update.

---

## 3. Core Tasks Breakdown

### Task 1: Define Editable Product Fields

In tier-1 multi-vendor e-commerce marketplaces, product listings require structured field controls to preserve catalog quality, search consistency, and logistics accuracy.

#### Field Classification & Rules Matrix

| Field Group | Field Name | Data Type | Editable? | Validation & Marketplace Rules |
| :--- | :--- | :--- | :---: | :--- |
| **Identity** | `product_id` | UUID | No | System-generated immutable primary key. |
| **Ownership** | `seller_id` | UUID | No | Derived strictly from authenticated seller session. Never client-editable. |
| **Basic Info** | `product_name` | String | Yes | Required. Length: 10 – 120 chars. Whitespace trimmed. Filtered against banned keywords and prohibited spam phrasing. |
| **Basic Info** | `category_id` | UUID | Yes | Required. Must exist in platform category tree. Changing category resets category-specific attributes. |
| **Basic Info** | `description` | Text | Yes | Required. Length: 20 – 3000 chars. Sanitized HTML/Markdown to prevent stored XSS. |
| **Media** | `cover_image_url` | URL String | Yes | Required. Primary display image on catalog cards. Aspect ratio 1:1 or 3:4. Validated HTTPS URL. |
| **Media** | `gallery_images` | Array[URL] | Yes | Optional (up to 8 additional images). Supports reordering, deletion, and addition of new media. |
| **Pricing** | `price` | Decimal(12,2) | Yes | Required. Must be strictly positive (`price > 0.00`). Guardrail alert if price changes by > ±80%. Locked if enrolled in active flash campaign. |
| **Pricing** | `original_price`| Decimal(12,2) | Yes | Optional comparison / struck-through price. Must satisfy `original_price >= price`. |
| **Inventory** | `stock_quantity`| Integer | Yes | Required. Non-negative integer (`stock >= 0`). Cannot be set below `reserved_stock`. |
| **Inventory** | `sku_code` | String | Yes | Optional internal merchant SKU. Alphanumeric, max 50 chars. |
| **Variations**| `variations` | JSONB / Array | Yes | Supports 1-tier or 2-tier variants (e.g., Color, Size). Each SKU has independent price and stock. |
| **Logistics** | `weight_grams` | Integer | Yes | Required. Package weight in grams (`weight > 0`). Used for automated freight calculation. |
| **Logistics** | `dimensions` | Object | Yes | Required. Length, Width, Height in cm (`> 0`). Used for volumetric shipping tier determination. |
| **Shipping** | `is_pre_order` | Boolean | Yes | If `false`: Ships in standard 2 business days. If `true`: Ships in 7 – 15 business days (`days_to_ship`). |
| **Listing** | `status` | Enum | Yes | `ACTIVE` (searchable & purchasable), `DELISTED` (hidden by seller), `OUT_OF_STOCK` (auto-derived when stock = 0). |

---

### Task 2: Define Stock Update Behaviour

Stock updates directly affect marketplace integrity and buyer checkout flows. The system adheres to real-time inventory management principles:

```
[ Physical Stock ] = [ Available Stock ] + [ Reserved Stock ]
```

1. **Stock Definitions**:
   - **Physical Stock (`stock_quantity`):** Total units physically available in the seller's inventory.
   - **Reserved Stock (`reserved_stock`):** Units temporarily locked for buyers currently in pending checkout/unpaid order status.
   - **Available Stock (`available_stock`):** Purchasable inventory visible on the catalog (`stock_quantity - reserved_stock`).
2. **Floor Constraint:**
   - A seller **cannot** reduce `stock_quantity` below the current `reserved_stock`.
   - *Formula:* `new_stock_quantity >= product.reserved_stock`. If violated, the system responds with `ERR_STOCK_BELOW_RESERVED`.
3. **Availability Transitions**:
   - **`stock_quantity == 0`**:
     - Product status automatically evaluates to **Out of Stock**.
     - Buyer catalog removes the item from active availability filters (aligned with **BR1**).
     - Product detail page shows "Hết hàng / Out of Stock" badge; purchase buttons are disabled.
   - **`stock_quantity > 0`**:
     - Product status immediately restores to **In Stock**.
     - Catalog index and search queries reflect renewed purchasing capability.
4. **Quick Inline Stock Update:**
   - From `/seller/products`, sellers can click directly on the stock cell to perform quick inline increments/decrements without navigating into the full edit form.

---

### Task 3: Define Product Ownership Rule

#### BR5 - Seller Product Ownership & Multi-Vendor Tenant Isolation
- Every product listing belongs strictly to the seller who created it.

  1. The API gateway / auth middleware verifies the JWT or session token.
  2. The authenticated user ID is extracted: `current_seller_id = request.user.id`.
  3. If no matching record is found:
     - If the product exists under another seller ID: HTTP `403 Forbidden` (`ERR_FORBIDDEN_OWNERSHIP`).
     - If the product does not exist at all: HTTP `404 Not Found` (`ERR_PRODUCT_NOT_FOUND`).
- **Security Rule:** Under no circumstances may the client specify or override `seller_id` in the request body or parameters.

---

### Task 4: Define Invalid-Update Behaviour

When invalid data is submitted, the system guarantees **ACID transactional integrity**:

1. **Atomic Rollback:**
   - The update is executed inside a single database transaction (`BEGIN ... COMMIT`).
   - If any validation rule fails (e.g., negative stock, price equal to zero, invalid media format, database constraint violation), a `ROLLBACK` is triggered immediately.
   - The previously committed state remains 100% untouched.
2. **Deterministic Validation Pipeline:**
   - **Step 1 (Schema & Type Check):** Validates required fields, numeric constraints (`price > 0`, `stock >= 0`), integer types, and string length limits.
   - **Step 2 (Business Rule Check):** Validates ownership (`BR5`), active promotion lock, and reserved stock boundary.
   - **Step 3 (Concurrency Check):** Validates `version` tag for optimistic locking.
3. **Frontend UI Form Preservation:**
   - The UI does not reload or reset user-entered values.
   - Field-level validation errors are mapped directly beneath the erroneous inputs (e.g., *"Price must be greater than 0"*, *"Stock cannot be negative"*).
   - A global toast / banner notifies: *"Update failed. Please correct the highlighted errors."*

---

### Task 5: Map Edit-Product Screen to Business Rules

| Business Rule ID | Business Rule Description | How `/seller/products/:productId/edit` Enforces It |
| :--- | :--- | :--- |
| **BR1** | Only available products can be displayed in the product catalog. | When seller updates stock to `0` or toggles status to `DELISTED`, the product is immediately suppressed from catalog browsing. When replenished (`> 0`), catalog visibility is restored. |
| **BR2** | Buyers can add products to cart only when requested quantity is available. | Stock changes immediately adjust maximum cart addition limits. If seller reduces stock below what a buyer has in their active cart, the cart displays an adjustment notice. |
| **BR5** | Sellers may create and manage only products belonging to their own store. Product ownership derived from authenticated seller identity. | Both the edit view router and the update API verify `product.seller_id == authenticated_user.id`. Requests targeting another seller's product return `403 Forbidden`. |
| **BR8** | Stock must be revalidated at checkout using latest stock data. | Concurrency-safe stock updates ensure checkout processes always query the authoritative, committed stock quantity. |
| **BR9** | Product updates must validate `price > 0` and `stock >= 0`. Invalid updates roll back atomically without altering prior valid data. | Enforced by strict server-side validation and database transaction boundaries. Any failure aborts update, leaving prior data intact. |

---


## 4. Non-Functional Requirements (NFRs)

- **Data Integrity & Consistency (ACID):** Partial updates are strictly banned. If any parameter fails validation, the database transaction rolls back completely.
- **Security & Authorization:**
  - Token-based verification: `seller_id` is never accepted from the request body.
  - Strict IDOR mitigation: Attempting to update another store's product ID immediately yields HTTP `403 Forbidden` and records an audit log entry.
  - XSS Protection: HTML/Markdown product descriptions must be sanitized on the server before storage.
- **Concurrency Control:** Employs Optimistic Concurrency Control (`version` column) to prevent the lost-update anomaly when multiple browser tabs or background order processes interact with the same product.
- **Performance & Latency:**
  - Update API response time: `p95 < 200ms`.
  - Cache Invalidation: Catalog and product detail cache keys are invalidated synchronously upon successful transaction commit.
- **Auditability:** Every stock and price modification is logged in `product_audit_logs` tracking timestamp, seller ID, old values, and new values.

---

## 5. Definition of Ready (DoR)

- [x] The whole team understands what 'done' means for this story.
- [x] It does not depend on an unfinished story from another team member.
- [x] It is small enough to finish inside one sprint (Estimated at 3 Story Points).
- [x] Acceptance criteria are written in unambiguous BDD format covering happy paths, edge cases, and security denial.
- [] API contract, error status codes, and PostgreSQL atomic update queries are defined.
- [x] Real-world marketplace mechanisms (locked fields, price bounds, reserved inventory, concurrency control) are specified.

---

## 6. Definition of Done (DoD) Checklist

- [X] Route `/seller/products/:productId/edit` loads the existing product data into the form correctly.
- [X] Product updates with valid data persist to the database and reflect immediately on buyer views (`/products`, `/products/:id`).
- [X] Stock updates accurately synchronize availability status (*In Stock* vs. *Out of Stock*).
- [X] Updating another seller's product is blocked at the backend with HTTP `403 Forbidden`.
- [X] Submitting invalid price (`<= 0`) or negative stock returns HTTP `422/400`, leaves previous database data unchanged, and displays inline UI errors.
- [X] Automated tests cover ownership enforcement, positive/negative validation, and optimistic locking.
- [X] Code is reviewed, approved, and merged into `main` according to project team policy.
- [X] `docs/traceability.md` is kept up-to-date with route and business rule mapping.

---

## r 7. Target Persona

### Persona 2 – Seller: Nguyễn Thị Lệ

- **Age:** 38
- **Occupation:** Online Children's Fashion Retailer / Shop Owner
- **Role:** Seller
- **Gender:** Female
- **Interview method:** Online
- **Interview date:** 18/09/2026

#### Background

Nguyễn Thị Lệ is an experienced online merchant based in Móng Cái, Quảng Ninh, specializing in children's fashion and apparel for over 10 years across various digital sales channels and multi-vendor marketplaces.

Operating from a major border trading hub with direct access to extensive apparel manufacturing sources, her store manages a large catalog of fast-moving seasonal children's clothing (summer sets, winter coats, festive dresses, school wear) spanning numerous sizes (1–12 years) and color variations.

As a seasoned seller, chị Lệ values operational speed, data accuracy, and reliability when managing product listings, updating inventory in real time across multiple sizes, and adjusting prices during seasonal campaigns.

#### Actual Goals

- Update product information (fabric materials, size charts, age recommendations, care instructions, high-resolution photos) swiftly and accurately.
- Synchronize stock levels immediately across all variants to avoid overselling and out-of-stock order cancellations.
- Rapidly replenish stock when new clothing shipments arrive at the Móng Cái warehouse or mark depleted sizes as out of stock.
- Adjust selling prices and discount structures for seasonal promotions without disrupting active listings.
- Avoid accidental pricing errors (e.g. entering 18,000 VND instead of 180,000 VND for a children's jacket).
- Ensure store products and listings are strictly protected against tampering by unauthorized parties or competing sellers.

#### Pain Points

- Managing multi-variant apparel (multiple size and color combinations) is time-consuming if edit tools are rigid or slow.
- Overselling risk: If stock updates fail to synchronize immediately, buyers purchase out-of-stock children's sizes, resulting in cancelled orders, penalty points, and customer dissatisfaction.
- Frustration with form resets: Losing long product descriptions, size guides, and uploaded images when a single validation error occurs during an update.
- Inventory discrepancies caused by concurrent edits when warehouse staff and shop assistants update stock simultaneously.
- Security concerns regarding unauthorized modifications to her shop's product listings.

#### Key Needs

- Responsive and intuitive product edit interface supporting multi-image galleries (product photos, fabric close-ups, measurement charts).
- Real-time stock synchronization and quick inline stock adjustments directly from the seller inventory dashboard.
- Clear inventory breakdown between physical stock, reserved stock, and available stock to safeguard pending orders.
- Resilient form validation that preserves entered data upon errors and provides specific, actionable field-level feedback.
- Safety guardrails for significant price alterations to prevent costly mistyping mistakes.
- Strict multi-vendor tenant isolation and ownership security (`HTTP 403 Forbidden` on unauthorized edit attempts).

#### Relationship to US07

US07 directly supports Nguyễn Thị Lệ's core operational need to keep her children's fashion listings accurate, competitive, and up to date.

The story addresses the persona's goals and pain points by:

- enabling fast and comprehensive updates to product descriptions, category attributes, media, and inventory quantities;
- immediately propagating stock changes to the buyer catalog so depleted children's sizes automatically display as *"Out of Stock"* and cannot be ordered;
- enforcing atomic rollback on invalid inputs (such as negative stock or zero price) so that previous valid listings remain completely intact and form inputs are preserved for easy correction;
- enforcing strict seller ownership (`BR5`) so that her Móng Cái store listings are protected against unauthorized modification;
- incorporating optimistic concurrency control to prevent inventory conflicts during high-volume sales periods.

