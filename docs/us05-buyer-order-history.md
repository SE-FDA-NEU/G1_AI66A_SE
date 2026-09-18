# US05 - View Buyer's Order History and Status

**Issue:** #17  
**Priority:** P1 - Should have  
**Story Points:** 3  
**Related routes:** `/orders`, `/orders/:id`

---

## 1. User Story

As a buyer, I want to view my previous orders and their current status,
so that I can track my purchases.

---

## 2. Order Summary Fields

When the buyer opens `/orders`, each order in the history must display
the minimum information required by the story:

- **Order ID** - uniquely identifies the order.
- **Order date** - shows when the order was created.
- **Total amount** - shows the total value of the order.
- **Current status** - shows the current state of the order.

The order history should display only orders belonging to the currently
authenticated buyer.

---

## 3. Order Detail Fields

When the buyer selects one of their orders, the system opens the
order-detail screen.

The order detail must display:

- Order ID
- Order date
- Current status
- Products included in the order
- Quantity of each product

The information shown on the detail screen must belong to the selected
order only.

---

## 4. Possible Order Statuses

To keep buyer and seller order information consistent, US05 uses the
following order statuses:

- **PENDING** - the order has been created and is waiting to be processed.
- **PROCESSING** - the order is being prepared by the seller.
- **SHIPPED** - the order has been handed over for delivery.
- **DELIVERED** - the order has been successfully delivered.
- **CANCELLED** - the order has been cancelled and will not continue
  through the delivery process.

The status shown to the buyer must reflect the latest valid state of the
order.

> Note: If a multi-seller order contains sub-orders with different statuses,
> the rule for deriving the parent order status should be agreed by the team
> during the design stage.

---

## 5. Access-Control Rule for Buyer Orders

### BR4 - A buyer can view only their own orders

A buyer must be authenticated before viewing order history or order details.

When requesting an order detail:

1. The system identifies the currently authenticated buyer.
2. The system checks whether the requested order belongs to that buyer.
3. If the order belongs to the buyer, the order detail is displayed.
4. If the order belongs to another buyer, access is denied.

A buyer must not be able to obtain another buyer's order information by
manually entering or modifying an order ID.

---

## 6. Empty Order History Behaviour

If the buyer has never placed an order:

- the `/orders` page must not display an empty or broken order list;
- the system displays an appropriate empty-state message;
- no order details are displayed.

Example message:

> You have not placed any orders yet.

---

## 7. Order History and Order Detail Flow

```text
Authenticated Buyer
        |
        v
     /orders
        |
        v
Load buyer's own orders
        |
        +---- No orders ----> Show empty-state message
        |
     Orders exist
        |
        v
Display:
- Order ID
- Date
- Total
- Status
        |
        v
Buyer selects an order
        |
        v
   /orders/:id
        |
        v
Check order ownership
        |
        +---- Not owner ----> Deny access
        |
      Owner
        |
        v
Display order details
        |
        v
Products + Quantities