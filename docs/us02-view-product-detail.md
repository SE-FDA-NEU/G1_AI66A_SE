# US02 - View Product Detail

**Issue:** #14  
**Priority:** P0 - Must have  
**Story Points:** 2  
**Related route:** `/products/:productId`

---

## 1. User Story

As a buyer, I want to view detailed information about a product, so that I can decide whether the product is suitable before purchasing it.

---

## 2. Product Detail Fields

When the buyer opens `/products/:productId`, the system must display the following information about the product:

- **Product name** – the full, untruncated name of the product.
- **Product price** – the formatted price (e.g., $99.99 or 150.000 ₫).
- **Product description** – a full-text description of the product.
- **Product image** – the main product image displayed at a readable size with appropriate `alt` text for accessibility.
- **Stock availability** – a clear indicator of whether the product is currently available for purchase.

All displayed information must correspond to the requested product only.

---

## 3. Stock Availability Display

The product detail page must clearly communicate the stock status of the product.

### In-stock product

If the product has available stock:

`stockQuantity > 0`

the system displays a positive availability indicator such as:

> In Stock

The buyer may proceed with adding the product to the cart (as defined by US03).

### Out-of-stock product

If the product has no available stock:

`stockQuantity = 0`

the system must clearly show that the product is unavailable for purchase.

The system must:

- display a visible out-of-stock indicator (e.g., "Out of Stock");
- disable or hide the "Add to Cart" action so that the buyer cannot attempt to add the product;
- not remove the product from the detail page — the buyer may still view its information.

Example message:

> Out of Stock

---

## 4. Product Not Found Behaviour

If the buyer navigates to `/products/:productId` and the product ID does not correspond to any existing product:

- the system must not display a blank or broken page;
- the system must display a clear "Product not found" message;
- the buyer should be provided with a way to return to the product catalogue.

This applies to:

- a product ID that has never existed;
- a product ID that has been deleted or is otherwise no longer available in the system.

Example message:

> Product not found.

---

## 5. Navigation and Context

### Entry from product catalogue

The primary entry point to the product detail page is the product catalogue (US01).

When a buyer clicks on a product card in `/products`, the system navigates to `/products/:productId`.

### Back to catalogue

The product detail page should provide a way to navigate back to the product catalogue.

---

## 6. Product Detail Page Flow

```text
/products (catalogue)
        |
        v
Buyer clicks product card
        |
        v
Navigate to /products/:productId
        |
        v
Fetch product by ID
        |
        +---- Product not found ----> Show "Product not found" message
        |                              + link back to catalogue
        |
     Product exists
        |
        v
Display:
- Name
- Price
- Description
- Image
- Stock availability
        |
        v
Stock > 0?
        |
        +---- No ----> Show "Out of Stock"
        |               Disable "Add to Cart"
        |
       Yes
        |
        v
Show "In Stock"
Enable "Add to Cart"
```

---

## 7. Loading State & Error Handling

### Loading state

While the system is fetching product data from the API:

- a loading indicator or skeleton UI should be displayed;
- the page must not show stale or incorrect data.

### API error

If the API returns an error (e.g., 500 Internal Server Error or timeout):

- the system must display a friendly error message;
- a "Retry" option should be provided so the buyer can re-attempt loading.

Example message:

> Something went wrong. Please try again later.

---

## 8. Relationship with Other Stories

### US01 - Browse Product Catalog

US01 provides the product catalogue from which the buyer navigates to the product detail page.

The product card in US01 links to `/products/:productId`.

### US03 - Shopping Cart

The product detail page enables the buyer to add the product to the cart, as defined in US03.

The "Add to Cart" action must respect the stock validation rules defined in US03 Section 6 (BR2).

### US06 - Create Product

The product information displayed in US02 is created by the seller through US06.

The fields displayed on the detail page (name, description, price, image, stock) correspond to the fields entered during product creation.

---

## 9. Acceptance Criteria Coverage

### Acceptance Criteria 1

Given a valid product exists, when I open its detail page, then I see its name, price, description, image and stock availability.

Covered by Sections 2 and 3.

### Acceptance Criteria 2

Given the product is out of stock, when I view the product, then the system clearly shows that it is unavailable for purchase.

Covered by Section 3 (Out-of-stock product).

### Acceptance Criteria 3

Given the product ID does not exist, when I open the URL, then the system shows a clear "Product not found" response.

