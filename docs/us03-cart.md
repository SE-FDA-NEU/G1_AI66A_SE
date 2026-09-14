# US03 - Add and Manage Products in Shopping Cart

**Issue:** #15  
**Priority:** P0 - Must have  
**Story Points:** 5  
**Related route:** `/cart`  

## 1. User Story

As a buyer, I want to add products to a shopping cart and change their quantities, so that I can prepare several products before placing an order. 

---

## 2. Cart Item Information

Each item in the shopping cart contains:

- Product identifier
- Product name
- Product image
- Unit price
- Selected quantity
- Line total

The line total is calculated as:

`lineTotal = unitPrice x quantity`

The cart total is calculated as:

`cartTotal = sum(lineTotal of all cart items)`

The total must be recalculated whenever an item is added, removed, or its qunatity is changed.

---

## 3. Add Product to Cart

When a buyer adds a product to the cart:

1. The system checks that the product exists/
2. The system checks that the product is currently available for purchase/
3. The selected quantity must be a positive integer.
4. The selected quantity must not exceed the currently available stock.
5. If validation succeeds, the item is added to the cart/
6. If the same product already exists in the cart, its quantity is increased instead of creating a duplicate cart line.
7. The resulting quantity must still satisfy the stock constraint.

If the validation fails, the cart must remain unchanged and the buyer must receive a clear error message.

---

## 4. Update Quantity

A buyer may change the quantity of an existing cart item.

A valid quantity must satisfy:

- It is an integer.
- It is greater than or equal to 1.
- It does not excceed the currently available stock.

If the requested quantity is invalid:

- the update is rejected;
- the previous valid quantiy remains unchanged;
- the cart total remains unchanged;
- the buyer is informed why the update failed.

Setting the quantity to zero is not treated as a quantity update. The buyer should use the remove action instead.

---

## 5. Remove Product

When a buyer removes an item:

1. The selected cart item is removed.
2. Other cart items remain unchanged.
3. The cart total is recalculated.
4. If the removed item was the last item, the cart enters the empty state.

---

## 6. Quantity & Shock Validation

### BR2 - Cart quantity validation

A buyer may add or update a cart item only when the requested quantity is a positive integer and does not exceed the product's currently available stock.

Adding a product to the shopping cart does not reserve stock/

Stock may change after a product has been added to the cart

Therefore, the cart preforms an initial stock validation for user feedback, but the final stock validation is performed again during checkout according to BR8.

This keeps US03 consistent with US04.

---

## 7. Empty Cart Behaviour

If the cart contains no product:

- the `/cart` screen displays a clear empty-state message;
- the cart total is displayed as zero;
- the buyer is provided with a way to return to the product catalogue;
- checkout must not create an order from the empty cart.

Suggested message:

`Your cart is empty.`

---

## 8. Unhappy Paths

The system must handle the following situations clearly.

### Product no longer exists

If a cart operation references a product that no longer exists:

- the operation is rejected;
- the buyer is informed that the product is unavailable.

### Product becomes unavailable

If a product is no longer available for sale:

- its quantity must not be increased;
- the buyer must be informed that the product is unavailable.

### Stock decreases

If available stock becomes lower than the requested cart quantity:

- the quantity update is rejected;
- the previous cart state remains unchanged;
- the buyer is informed of the available quantity.

### Invalid quantity

Negative, zero, fractional, or otherwise invalid quantities are rejected.

---

## 9. Cart Flow

```text
Product
   |
   v
Add to cart
   |
   v
Validate product
   |
   +---- Invalid ----> Show error
   |
  Valid
   |
   v
Validate quantity against current stock
   |
   +---- Invalid ----> Show stock/quantity error
   |
  Valid
   |
   v
Update cart
   |
   v
Recalculate total
   |
   v
/cart
   |
   v
Checkout
   |
   v
Revalidate latest stock according to BR8
```

---

## 10. Relationship with US04

US03 prepares products for checkout, while US04 performs final order creation.

The cart must never assume that stock checked when an item was added is still valid at checkout time.

US04 therefore remains responsible for:

- checking latest product availability;
- checking latest stock;
- preventing overselling;
- creating the final order.

---

## 11. Acceptance Criteria Coverage

### AC1

Given a product has available stock, when the buyer adds it to the cart, the product appears with the selected quantity.

Covered by Sections 3 and 6.

### AC2

Given a product is already in the cart, when its quantity changes, the cart total is recalculated.

Covered by Sections 2 and 4.

### AC3

Given a product is in the cart, when it is removed, the item disappears and the total is updated.

Covered by Section 5.

### AC4

Given the requested quantity exceeds available stock, the update is rejected with a clear message.

Covered by Sections 4, 6 and 8.

---