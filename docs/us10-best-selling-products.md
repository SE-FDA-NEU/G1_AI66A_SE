# US10 - Seller Views Best-Selling Products

- **Issue:** #22
- **Epic:** F6 Analytics
- **Priority:** P2 - Nice to have
- **Story Points:** 3
**Related route:** `/seller/analytics/products`

---

## 1. User Story

As a seller, I want to see which of my products sell the most,
so that I can make better inventory and sales decisions.

---

## 2. Feature Overview

The best-selling product analytics page shows a seller which of their own
products have sold the highest quantity in completed orders.

The page must allow the seller to:

- view a ranked list of best-selling products;
- understand the quantity sold for each ranked product;
- filter the ranking by date range;
- see a clear empty state when no eligible sales exist;
- avoid seeing sales data belonging to other sellers.

US10 focuses on product quantity ranking. Revenue analytics are handled by US09.

---

## 3. Best-Selling Ranking Metric

Best-selling products are ranked by **total quantity sold**.

For each product `p` belonging to the authenticated seller:

```text
Total Quantity Sold(p) = Sum(orderItem.quantity)
```

where each counted order item satisfies all of the following:

- the product belongs to the authenticated seller;
- the parent order has status `COMPLETED`;
- the order completion timestamp belongs to the selected reporting period.

Products with a higher total quantity sold appear above products with a lower
total quantity sold.

If two products have the same total quantity sold, the ranking should use a
stable secondary sort, such as product name ascending and then product ID. This
keeps the display deterministic for users and tests.

Revenue is not used as the primary ranking metric for US10.

Products with no eligible sales in the selected period do not need to appear in
the ranking. If no products have eligible sales, the empty-state behaviour in
Section 6 applies.

---

## 4. Eligible Orders for Calculation

Only sales from **completed orders** are eligible for the best-selling product
calculation.

The ranking must not include quantities from orders that are still:

- pending;
- processing;
- shipped;
- cancelled;
- rejected;
- refunded.

This keeps the report based on completed sales rather than unfinished,
cancelled, or invalid transactions.

This behaviour is consistent with BR7 in `docs/traceability.md`:

> Seller analytics must be calculated from completed or valid order data.

---

## 5. Date-Range Behaviour

When the seller selects a date range, the ranking must be calculated using only
completed orders whose completion date falls within the selected period.

The relevant timestamp is:

```text
completedAt
```

rather than the order creation timestamp.

For a selected range:

```text
from <= completedAt <= to
```

Example:

```text
Selected range:
01/09/2026 - 30/09/2026

Included:
Orders completed during this period.

Excluded:
Orders completed before 01/09/2026 or after 30/09/2026.
```

Changing the date range causes the ranking to be recalculated for the new
period.

To stay consistent with US09, the default date range should be `All time` when
the seller has not selected a narrower range.

For a custom date range:

- both start and end dates must be valid;
- the start date must not be later than the end date;
- an invalid range must display a validation message;
- the ranking must not refresh using an invalid range.

Suggested validation message:

`Start date must be earlier than or equal to end date.`

---

## 6. No-Sales-Data Behaviour

If no eligible completed sales exist for the selected reporting period, the
system must not display an empty or misleading ranking.

Instead, the system displays:

`No sales data available`

No product should be shown with an artificial sales quantity when no eligible
sales data exists.

An empty result is not an application error.

---

## 7. Seller-Only Data Isolation

### BR10 - Seller best-selling analytics must contain only the seller's own product data

The authenticated seller must see ranking data only for products belonging to
their own store.

When calculating best-selling products:

1. The system identifies the authenticated seller from the session or
   authorization context.
2. Only products belonging to that seller are considered.
3. Only eligible completed order items for those products are aggregated.
4. Products and sales belonging to other sellers are excluded.

The client must not be able to provide an arbitrary seller ID to view another
seller's analytics.

This rule also applies when a buyer's order contains products from multiple
sellers. A seller must never see another seller's product sales included in
their ranking.

---

## 8. UI States

### Loading State

While the ranking is being retrieved, the page displays a loading indicator or
skeleton state.

Suggested text:

`Loading product analytics...`

### Success State

When data is available, the page displays a ranked list containing at least:

- rank;
- product name or identifier;
- total quantity sold for the selected period.

The selected date range should be visible so the seller understands the period
represented by the ranking.

### Empty State

When no eligible sales exist, the page displays:

`No sales data available`

### Error State

If analytics cannot be loaded because of a system, network, or server error,
the application must distinguish this from an empty result.

Suggested message:

`Unable to load product analytics. Please try again.`

Suggested action:

`Retry`

---

## 9. Best-Selling Product Analytics Flow

```text
Authenticated seller
        |
        v
/seller/analytics/products
        |
        v
Select or use date range
        |
        v
Validate date range
        |
        +---- Invalid ----> Show validation message
        |
      Valid
        |
        v
Load seller's own products
        |
        v
Find completed order items
within selected period
        |
        +---- No sales ----> "No sales data available"
        |
     Sales exist
        |
        v
Sum quantity sold
for each product
        |
        v
Sort by quantity sold
descending
        |
        v
Display best-selling
product ranking
```

---

## 10. Acceptance Criteria

### AC1 - Rank products by quantity sold

**Given** completed orders containing my products exist,
**when** I open product analytics,
**then** products are ranked by total quantity sold from eligible completed
orders.

### AC2 - Filter ranking by date range

**Given** I choose a valid date range,
**when** the ranking is generated,
**then** only completed orders whose `completedAt` timestamp falls within that
period are counted.

### AC3 - Empty sales period

**Given** there is no eligible sales data,
**when** I open the report,
**then** the system displays `No sales data available`.

### AC4 - Seller data isolation

**Given** products from other sellers exist,
**when** my best-selling product ranking is calculated,
**then** those products and their sales are not included in my ranking.

---

## 11. Traceability to Issue #22

| Original requirement | Covered by |
|---|---|
| Products ranked by quantity sold | Sections 3, 9; AC1 |
| Completed orders only | Sections 3, 4; AC1 |
| Date-range filtering | Section 5; AC2 |
| No sales data message | Section 6; AC3 |
| Seller-only data isolation | Section 7; AC4 |
| Related route `/seller/analytics/products` | Header, Sections 8-9 |

---

## 12. Persona Relevance

US10 primarily supports the Seller persona, Trần Hoàng Nam.

The seller wants to manage inventory efficiently and understand sales
performance. One of the seller's pain points is the lack of clear information
about which products perform well.

US10 addresses this need by:

- identifying which products sell the most;
- allowing sales performance to be viewed for a selected period;
- using completed sales so the ranking is based on actual purchases;
- excluding other sellers' data from the report.

This information can help the seller make better inventory and sales decisions
without exposing data belonging to other sellers.

---

## 13. Out of Scope for US10

To keep US10 within its current story scope, the following features are not
required:

- ranking products by revenue;
- showing profit or cost analytics;
- exporting the ranking;
- comparing one seller against another seller;
- marketplace-wide best-selling product analytics;
- forecasting future best-selling products.
