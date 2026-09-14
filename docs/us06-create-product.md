# US06 - Seller creates a product listing

**Issue:** #18  
**Priority:** P0 - Must have  
**Story Points:** 5  
**Related route:** `/seller/products/new`

## 1. User Story

As a seller, I want to create a product listing, so that buyers can discover and purchase my products.

---


## 2. Required Product Fields

A seller must provide the following information when creating a product:

- Product name
- Product description
- Product price
- Stock quantity
- Product image

The system also associates the product with the authenticated seller.

The seller identity must not be trusted from user-provided form data.

---


## 3. Product Validation Rules

### Product name

- Required.
- Must not be empty after trimming whitespace.

### Description

- Required.
- Must not be empty after trimming whitespace.

### Price

- Required.
- Must be numeric.
- Must be strictly greater than zero.

Therefore:

`price > 0`

### Stock quantity

- Required.
- Must be an integer.
- Must be greater than or equal to zero.

Therefore:

`stockQuantity ∈ Integer`

`stockQuantity >= 0`

A stock quantity of zero is valid, but the product is considered out of stock.

### Product image

A product image must be provided using the image mechanism selected by the application architecture.

The exact storage mechanism is deferred to the implementation/design milestone.

---


## 4. Seller Authorization

Only an authenticated seller may access product creation.

The authorization flow is:

```text
Request /seller/products/new
          |
          v
Authenticated?
     |          |
    No         Yes
     |          |
 Reject      Role == Seller?
                  |        |
                 No       Yes
                  |        |
                Reject   Allow
```

An unauthenticated user must not be allowed to create products.

An authenticated user without seller privileges must also be denied access.

---


## 5. Product Ownership

### BR5 - Seller product ownership

Every newly created product belongs to the authenticated seller who created it.

The product owner must be derived from the authenticated identity.

Conceptually:

`sellerId = authenticatedUser.id`

The application must not trust an arbitrary `sellerId` provided by the client.

This prevents one seller from creating or managing products on behalf of another seller.

---


## 6. Product Creation Flow

---


## 7. Invalid Input Behaviour

---


## 8. Product Visibility

---


## 9. Seller Persona Relationship

---

