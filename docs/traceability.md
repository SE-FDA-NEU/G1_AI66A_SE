# Traceability

Every screen traces back to a feature and forward to the issue that built it.

This table is the single source of truth for Milestone 1 section 6 and for the
Milestone 4 report. Keep it current - a PR that adds a route and does not
update this file should not be approved.

| Route | Purpose | Access | Priority | Feature | Story issue | PR | Status |
|-------|---------|--------|----------|---------|-------------|-----|--------|
| `/products` | Browse product catalog | G | P0 | F1 Product Discovery | TBD | TBD | Not started |
| `/products/:id` | View product details | G | P0 | F1 Product Discovery | TBD | TBD | Not started |
| `/cart` | Manage shopping cart | U | P0 | F2 Cart | TBD | TBD | Not started |
| `/checkout` | Place an order | U | P0 | F3 Ordering | TBD | TBD | Not started |
| `/orders` | View buyer orders | U | P1 | F3 Ordering | TBD | TBD | Not started |
| `/seller/products` | Manage seller products | U | P0 | F4 Product Management | TBD | TBD | Not started |
| `/seller/orders` | Manage incoming orders | U | P0 | F5 Order Management | TBD | TBD | Not started |
| `/seller/analytics` | View sales analytics | U | P1 | F6 Analytics | TBD | TBD | Not started |

**Access codes:** G = guest (not logged in) · U = authenticated user · A = admin

**Status:** Not started / In progress / Done

## Business rules

Numbered, so issues and tests can cite them.

| # | Rule | Enforced where | Tested by |
|---|------|----------------|-----------|
| BR1 | Only available products can be displayed in the product catalog. | Product catalog | TBD |
| BR2 | Buyers can add products to their shopping cart only when the requested quantity is available. | Cart | TBD |
| BR3 | A buyer must be authenticated before placing an order. | Checkout | TBD |
| BR4 | A buyer can view only their own orders. | Orders | TBD |
| BR5 | Sellers can manage only products belonging to their own store. | Seller product management | TBD |
| BR6 | Sellers can view and manage incoming orders related to their products. | Seller order management | TBD |
| BR7 | Seller analytics must be calculated from completed or valid order data. | Seller analytics | TBD |