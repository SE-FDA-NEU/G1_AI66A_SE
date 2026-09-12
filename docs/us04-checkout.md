# US04 - Place an Order from Shopping Cart

**Issue:** #16  
**Priority:** P0 - Must have  
**Story Points:** 5  
**Related route:** `/checkout`

## 1. User Story

As a buyer, I want to place an order using the products in my cart,
so that I can complete my purchase.

---

## 2. Checkout Input Requirements

To confirm an order, the buyer must provide valid delivery information.

Required checkout information:

- Recipient name
- Delivery address
- Phone number
- Products currently contained in the shopping cart
- Quantity of each product

The system must validate the checkout information before creating an order.

An order must not be created when:

- the shopping cart is empty;
- required delivery information is missing or invalid;
- a product is no longer available;
- the requested quantity exceeds the available stock.

---

## 3. Order Creation Flow

1. Buyer opens the `/checkout` page.
2. System displays products currently in the shopping cart.
3. System displays the quantity and price of each item.
4. System calculates the order total.
5. Buyer enters delivery information.
6. Buyer selects **Confirm Order**.
7. System validates the delivery information.
8. System validates the shopping cart.
9. System checks current product availability and stock.
10. If all validations pass, the system creates the order.
11. The order stores the correct products, quantities and total amount.
12. System generates an order identifier.
13. System displays an order confirmation to the buyer.

---

## 4. Stock Validation at Checkout

Stock must be checked again when the buyer confirms the order.

The system must not rely only on the stock information displayed when
the product was originally added to the cart because stock may have
changed before checkout.

For every cart item, the system verifies:

- the product still exists;
- the product is available for sale;
- available stock is greater than or equal to the requested quantity.

If one or more items fail validation:

- the order is not created;
- no stock is deducted;
- the buyer is informed which item caused the problem;
- the buyer may return to the cart and update the quantity or remove
  the unavailable item.

---

## 5. Empty Cart Behaviour

If the shopping cart contains no items:

1. The system prevents the buyer from confirming checkout.
2. No order record is created.
3. The buyer receives a message explaining that the cart is empty.
4. The buyer can return to the product catalogue to add products.

---

## 6. Concurrency Business Rule

### BR8 - Stock must be validated at order confirmation

When multiple buyers attempt to purchase the same product at the same
time, stock availability must be checked using the latest stock value
at the moment the order is confirmed.

An order may only be created when sufficient stock is still available.

The system must ensure that two simultaneous checkout requests cannot
successfully purchase more units than the available stock.

If stock becomes insufficient before an order is completed, that order
must be rejected and the buyer must be informed which product is no
longer available in the requested quantity.

---

## 7. Checkout to Order Confirmation Flow

```text
Shopping Cart
     |
     v
 /checkout
     |
     v
Enter delivery information
     |
     v
Confirm order
     |
     v
Validate input
     |
     +---- Invalid ----> Show validation error
     |
    Valid
     |
     v
Check cart
     |
     +---- Empty ------> Prevent order creation
     |
 Not empty
     |
     v
Validate product availability and stock
     |
     +---- Invalid ----> Show problematic item
     |
    Valid
     |
     v
Calculate final total
     |
     v
Create order
     |
     v
Generate order ID
     |
     v
Order confirmation
```

## 8. Persona Relevance

US04 primarily supports the Buyer persona, Nguyễn Minh Anh.

This story supports the buyer's goal of completing purchases conveniently
through the `/checkout` flow.

It addresses the buyer's key needs by:

- allowing checkout from the shopping cart;
- validating cart quantities and product availability;
- preventing invalid orders when stock is insufficient;
- providing an order identifier and confirmation after successful checkout.

Therefore, US04 directly addresses the buyer's need for a reliable and clear
checkout process.