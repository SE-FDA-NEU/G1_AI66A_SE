## 2. Data Model

The Mini Marketplace uses a relational database model to support the P0 buyer and seller workflows defined in Milestone 1.

The data model contains six main tables:

- `users`
- `products`
- `cart_items`
- `orders`
- `seller_orders`
- `order_items`

The current implementation already contains the `products` table through the `Product` SQLModel. The remaining tables define the relational structure required to support cart management, checkout, seller ownership, and seller order management.

---

### 2.1 Entity Relationship Diagram

![Mini Marketplace ERD](images/design_erd.png)

---

### 2.2 Table Definitions

#### users

**Purpose:** Stores marketplace user accounts. A user may act as a buyer or seller depending on the assigned role.

| Column | Type | Constraints |
|---|---|---|
| `id` | INTEGER | Primary Key |
| `name` | VARCHAR(100) | NOT NULL |
| `email` | VARCHAR(255) | NOT NULL, UNIQUE |
| `role` | VARCHAR(20) | NOT NULL |
| `created_at` | DATETIME | NOT NULL |

The `role` field identifies whether the user is permitted to perform buyer or seller operations.

---

#### products

**Purpose:** Stores products listed by sellers together with their current inventory information.

| Column | Type | Constraints |
|---|---|---|
| `id` | INTEGER | Primary Key |
| `code` | VARCHAR(20) | NOT NULL, UNIQUE |
| `seller_id` | INTEGER | NOT NULL, Foreign Key → `users.id` |
| `name` | VARCHAR(200) | NOT NULL |
| `description` | TEXT | Optional |
| `price` | INTEGER | NOT NULL, CHECK `price > 0` |
| `stock_quantity` | INTEGER | NOT NULL, DEFAULT 0, CHECK `stock_quantity >= 0` |
| `reserved_stock` | INTEGER | NOT NULL, DEFAULT 0, CHECK `reserved_stock >= 0` |
| `image_url` | TEXT | Optional |
| `is_active` | BOOLEAN | NOT NULL, DEFAULT TRUE |
| `version` | INTEGER | NOT NULL, DEFAULT 1, CHECK `version >= 1` |

Additional inventory constraint:

```text
reserved_stock <= stock_quantity
```

Each product belongs to one seller through `seller_id`.

The current implementation already uses these fields in the `Product` SQLModel. The existing `seller_id` field is finalized by this design as a foreign key to `users.id`.

`thumbnail_url` is not stored as a separate database column. The product API can derive the public thumbnail URL from the stored `image_url` value.

---

#### cart_items

**Purpose:** Stores products that a buyer has currently added to their shopping cart.

| Column | Type | Constraints |
|---|---|---|
| `id` | INTEGER | Primary Key |
| `buyer_id` | INTEGER | NOT NULL, Foreign Key → `users.id` |
| `product_id` | INTEGER | NOT NULL, Foreign Key → `products.id` |
| `quantity` | INTEGER | NOT NULL, CHECK `quantity > 0` |
| `created_at` | DATETIME | NOT NULL |

Additional constraint:

```text
UNIQUE(buyer_id, product_id)
```

This constraint prevents the same product from appearing as multiple separate cart lines for the same buyer.

When a buyer adds the same product again, the existing cart item's quantity should be updated rather than creating another cart line.

The cart does not permanently reserve stock. Product availability must be checked again during checkout.

---

#### orders

**Purpose:** Stores the main marketplace order created by a buyer during checkout.

| Column | Type | Constraints |
|---|---|---|
| `id` | INTEGER | Primary Key |
| `buyer_id` | INTEGER | NOT NULL, Foreign Key → `users.id` |
| `total_amount` | INTEGER | NOT NULL, CHECK `total_amount >= 0` |
| `status` | VARCHAR(30) | NOT NULL |
| `recipient_name` | VARCHAR(100) | NOT NULL |
| `delivery_address` | TEXT | NOT NULL |
| `phone_number` | VARCHAR(20) | NOT NULL |
| `created_at` | DATETIME | NOT NULL |

Each order belongs to one buyer.

A marketplace order may contain products from multiple sellers. Therefore, seller-specific fulfillment is represented separately through the `seller_orders` table.

---

#### seller_orders

**Purpose:** Represents the seller-specific part of a marketplace order so that each seller can view and manage only the products belonging to them.

| Column | Type | Constraints |
|---|---|---|
| `id` | INTEGER | Primary Key |
| `order_id` | INTEGER | NOT NULL, Foreign Key → `orders.id` |
| `seller_id` | INTEGER | NOT NULL, Foreign Key → `users.id` |
| `status` | VARCHAR(30) | NOT NULL |
| `created_at` | DATETIME | NOT NULL |
| `completed_at` | DATETIME | NULL; set when status becomes `COMPLETED` |

Additional constraint:

```text
UNIQUE(order_id, seller_id)
```

This ensures that one seller has only one seller-specific order inside a given marketplace order.

The `status` field allows each seller to manage their own fulfillment process independently from other sellers participating in the same buyer order.

The `completed_at` field records when the seller-specific order reaches the `COMPLETED` state. It remains `NULL` while the seller order has not been completed.

For seller analytics, `seller_orders.status` is the canonical fulfillment status. Revenue and best-selling calculations include only seller orders where:

```text
seller_orders.status = COMPLETED
```

The selected analytics period is evaluated using `seller_orders.completed_at`, not the original marketplace order creation timestamp.

---

#### order_items

**Purpose:** Stores individual purchased products belonging to a seller order.

| Column | Type | Constraints |
|---|---|---|
| `id` | INTEGER | Primary Key |
| `seller_order_id` | INTEGER | NOT NULL, Foreign Key → `seller_orders.id` |
| `product_id` | INTEGER | NOT NULL, Foreign Key → `products.id` |
| `quantity` | INTEGER | NOT NULL, CHECK `quantity > 0` |
| `unit_price` | INTEGER | NOT NULL, CHECK `unit_price > 0` |

The `unit_price` field stores the product price at the time of purchase.

This value must be stored separately from the current `products.price` because a seller may change the product price after an order has already been created.

Example:

```text
Product price when ordered: 180,000
Current product price later: 200,000
Stored order_items.unit_price: 180,000
```

Historical orders and seller revenue therefore remain correct even when current product prices change.

---

### 2.3 Relationships and Cardinality

| Relationship | Cardinality | Description |
|---|---|---|
| `users` → `products` | 1 to 0..* | One seller may own zero or many products; each product belongs to one seller |
| `users` → `cart_items` | 1 to 0..* | One buyer may have zero or many cart items |
| `products` → `cart_items` | 1 to 0..* | One product may appear in zero or many buyers' carts |
| `users` → `orders` | 1 to 0..* | One buyer may create zero or many orders |
| `orders` → `seller_orders` | 1 to 1..* | One marketplace order contains one or more seller-specific orders |
| `users` → `seller_orders` | 1 to 0..* | One seller may receive zero or many seller orders |
| `seller_orders` → `order_items` | 1 to 1..* | One seller order contains one or more purchased items |
| `products` → `order_items` | 1 to 0..* | One product may appear in zero or many historical order items |

---

### 2.4 Relationship Summary

The main relationships can be summarized as follows:

```text
users
 ├──< products
 ├──< cart_items
 ├──< orders
 └──< seller_orders

products
 ├──< cart_items
 └──< order_items

orders
 └──< seller_orders

seller_orders
 └──< order_items
```

A buyer creates one marketplace `order`.

If the order contains products from multiple sellers, the order is divided into multiple `seller_orders`.

Example:

```text
Order #100
│
├── Seller Order A
│   ├── Wireless Mouse
│   └── Mechanical Keyboard
│
└── Seller Order B
    └── Laptop Stand
```

This structure allows each seller to view and manage only their own portion of the marketplace order.

---

### 2.5 Business Rule Mapping

Important relational constraints are mapped to the Milestone 1 business rules below.

| Database Constraint / Design Decision | Milestone 1 Rule | Purpose |
|---|---|---|
| `products.price > 0` | BR9 | Prevents zero or negative product prices |
| `products.stock_quantity >= 0` | BR9 | Prevents negative inventory |
| `products.reserved_stock >= 0` | BR9 | Prevents invalid reserved stock |
| `products.reserved_stock <= products.stock_quantity` | BR9 | Ensures reserved stock does not exceed available stock |
| `products.seller_id → users.id` | BR5 | Associates each product with its owning seller |
| `cart_items.quantity > 0` | BR2 | Ensures buyers can only place positive quantities in a cart |
| `UNIQUE(buyer_id, product_id)` | BR2 | Prevents duplicate cart lines for the same buyer and product |
| `orders.buyer_id → users.id` | BR3 / BR4 | Associates an order with the buyer who created it |
| `seller_orders.seller_id → users.id` | BR6 | Supports seller-specific order ownership |
| `UNIQUE(order_id, seller_id)` | BR6 | Creates one seller-specific order per seller inside a marketplace order |
| `order_items.unit_price` | BR7 | Preserves purchase-time prices for historical revenue calculations |
| `order_items.quantity > 0` | BR7 / BR10 | Ensures purchased quantities used in revenue and analytics are valid |
| `seller_orders.status = COMPLETED` | BR7 / BR10 | Ensures revenue and best-selling analytics include only completed seller sales |
| `seller_orders.completed_at` | BR7 / BR10 | Provides the completion timestamp used to filter analytics by selected period |

Some Milestone 1 business rules require application-level or transaction-level validation in addition to database constraints.

---

### 2.6 Transaction-Level Rules

Some business rules cannot be enforced using only static relational constraints.

In particular, stock must be revalidated immediately before an order is created.

The checkout operation should perform the following steps inside one database transaction:

```text
1. Read the buyer's current cart.
2. Re-read the current product inventory.
3. Verify that every requested quantity is still available.
4. Reject checkout if any product is unavailable.
5. Create the marketplace order.
6. Create the required seller orders.
7. Create order items using purchase-time prices.
8. Update product inventory.
9. Commit the transaction.
```

If any step fails, the transaction must roll back so that no partial order or inconsistent stock update remains.

A database transaction alone is not sufficient to prevent overselling when multiple checkout requests update the same product concurrently.

The design uses optimistic concurrency control through `products.version`.

For each product during checkout:

```text
1. Read the latest stock_quantity and version.
2. Verify that the requested quantity is available.
3. Update the product only if its version is still unchanged.
4. Decrease stock and increment version atomically.
5. If no row is updated, another transaction changed the product first;
   reject the checkout and revalidate instead of creating the order.
```

Conceptually:

```sql
UPDATE products
SET stock_quantity = stock_quantity - :quantity,
    version = version + 1
WHERE id = :product_id
  AND version = :expected_version
  AND stock_quantity >= :quantity;
```

If the update affects zero rows, checkout must fail or revalidate.

The inventory update and creation of `orders`, `seller_orders`, and `order_items` remain inside the same transaction. If any step fails, the complete transaction is rolled back.

This strategy supports BR8 by ensuring that the latest inventory is revalidated and updated atomically before order creation.

---

### 2.7 Implementation Consistency Notes

The current `Product` implementation uses an integer primary key.

The implemented product model contains the following database fields:

```text
id
code
seller_id
name
description
price
stock_quantity
reserved_stock
image_url
is_active
version
```

The public product API may expose derived response fields that are not separate database columns.

For example:

```text
thumbnail_url
stock_status
```

`thumbnail_url` can be derived from `image_url`.

`stock_status` can be calculated from `stock_quantity`.

Therefore, these derived API fields do not need to be stored separately in the relational schema.

The current implementation filters the public product catalog using:

```text
is_active = true
```

#### Product visibility terminology

`is_active` is the canonical persistence field used by the current Product model and by this relational design.

Milestone 1 BR1 also describes purchasable products as active.

If earlier API documentation uses `is_published`, it refers to the same catalog-visibility concept. The project should standardize on `is_active` rather than storing both `is_active` and `is_published`.

Therefore, the relational schema contains only:

```text
is_active
```

The ERD and table definitions in this document therefore retain the existing `is_active` field.

The current `seller_id` field exists in the Product model but is not yet implemented as a foreign key. This database design finalizes the intended relationship as:

```text
products.seller_id → users.id
```

The implementation should be updated later to reflect this relationship when the complete user and seller models are introduced.

---

### 2.8 Data Model Summary

The relational model contains six tables:

| Table | Main Responsibility |
|---|---|
| `users` | Stores buyer and seller accounts |
| `products` | Stores seller-owned marketplace products and inventory |
| `cart_items` | Stores products currently selected by buyers |
| `orders` | Stores buyer marketplace orders |
| `seller_orders` | Separates each marketplace order by seller |
| `order_items` | Stores purchased products, quantities, and purchase-time prices |

Together, these tables support the core P0 workflows required by the Mini Marketplace:

```text
Browse products
      ↓
Add products to cart
      ↓
Checkout
      ↓
Create buyer order
      ↓
Split order by seller
      ↓
Store purchased items
      ↓
Seller manages own order
```

The ERD in `docs/images/design_erd.png` must remain consistent with all table definitions, primary keys, foreign keys, and cardinalities documented in this section.
