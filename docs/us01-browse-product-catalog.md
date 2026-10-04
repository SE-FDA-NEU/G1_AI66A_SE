# User Story: Browse Product Catalog (Detailed)

## 1. Meta Information
- **Ticket ID:** US01
- **Epic:** Product Discovery
- **Story:** As a potential buyer, I want to browse products available on the marketplace, so that I can discover items I may want to purchase.
- **Priority:** P0 (Must Have)
- **Story Points:** 3
- **Target Platform:** Web (Desktop & Mobile Responsive)

## 2. Detailed Acceptance Criteria (BDD Format)

**Scenario 1: Viewing available products (Happy Path)**
- **Given** there are active products in the database
- **When** the user navigates to `/products`
- **Then** a product grid is displayed
- **And** each product card shows:
  - High-quality Thumbnail Image (with `alt` text for accessibility)
  - Product Name (truncated to 2 lines maximum)
  - Formatted Price (e.g., $99.99 or 150.000 ₫)
  - Availability Badge (e.g., "In Stock", "Only 2 left")

**Scenario 2: Navigating to Product Details**
- **Given** the user is viewing the product catalog
- **When** the user clicks on any product card
- **Then** the system navigates to the Product Detail Page (`/products/{id}`)

**Scenario 3: Empty Catalog State**
- **Given** there are no active products in the database
- **When** the user navigates to `/products`
- **Then** the product grid is hidden
- **And** an empty state illustration is shown with the text "No products available at the moment."
- **And** a "Return to Home" Call-to-Action (CTA) button is displayed.

**Scenario 4: Handling Pagination / Load More**
- **Given** there are more than 20 products available
- **When** the user scrolls to the bottom of the page (or clicks "Load More")
- **Then** the next batch of 20 products is fetched and appended to the grid without reloading the entire page.

**Scenario 5: Loading State & Error Handling**
- **Given** the user requests the `/products` page
- **When** the system is fetching data from the API
- **Then** a skeleton loading UI is displayed to indicate background processing.
- **But if** the API returns a 500 error or times out,
- **Then** a friendly error message "Something went wrong. Please try again later." is displayed with a "Retry" button.

## 3. Technical Implementation Details

### Backend & API
- **Endpoint:** `GET /api/v1/products?page={page}&limit={limit}` (`page >= 1`, `1 <= limit <= 100`, default `limit` 20)
- **Database Query** (SQLModel in `src/api/products.py`; equivalent SQL):
  - `SELECT COUNT(*) FROM products WHERE is_active = TRUE`
  - `SELECT * FROM products WHERE is_active = TRUE ORDER BY id LIMIT {limit} OFFSET {offset}`
- **Identifiers:** the internal primary key is an integer, returned as a string in `id`; `code` is the readable product code (for example `P-100`).
- **Response Payload Example (Success):**
  ```json
  {
    "data": [
      {
        "id": "1",
        "code": "P-100",
        "name": "Wireless Mouse",
        "description": "Wireless mouse for study and office work",
        "price": 180000.0,
        "thumbnail_url": "/images/p-100.jpg",
        "image_url": "/images/p-100.jpg",
        "stock_quantity": 12,
        "stock_status": "in_stock"
      }
    ],
    "meta": {
      "current_page": 1,
      "limit": 20,
      "total": 45,
      "total_pages": 3
    }
  }
  ```
- **Errors:** an invalid `page` or `limit` returns `422`; a failed database query returns `500` with `{"detail": "Unable to load products right now. Please try again later."}`.

### Frontend UI/UX
- **State Management:** Implement tracking for `isLoading`, `isError`, and `products[]`.
- **Components Required:** `ProductCard.tsx`, `EmptyState.tsx`, `SkeletonLoader.tsx`.

### 4. Non-Functional Requirements (NFRs)
- **Performance:** API response time must be under 300ms. Images must be lazy-loaded to optimize rendering speed (LCP).
- **Accessibility (a11y):** All product cards must be keyboard navigable (using `Tab`). Screen readers must be able to read the product name and price correctly.
- **Responsiveness:**
  - Desktop view: 4 product cards per row.
  - Tablet view: 3 product cards per row.
  - Mobile view: 2 product cards per row.

## 5. Definition of Ready (DoR)
- [ ] UI/UX Mockups are attached (Figma link).
- [x] API contract is defined.
- [x] Acceptance criteria cover edge cases (loading, empty, error).