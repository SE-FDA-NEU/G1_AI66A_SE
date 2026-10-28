# US15 — Product reviews and in-app notifications

US15 lets a buyer review a product only through a completed purchase, lets the
product's seller reply, and gives buyers and sellers a small in-app notification
center. The screens follow the shared navigation and interaction patterns documented
in [ui.md](ui.md), including the seller-order states from US14 / #106.

## Review flow

On `/products/{productCode}`, the public review list shows the aggregate rating,
verified-purchase reviews, optional comments/media links, and seller replies. A
signed-in buyer sees the review form only when the API finds a completed order item
for that product that has not already been reviewed. The form accepts a rating from
1 to 5, an optional comment, and an optional absolute HTTP(S) media URL; file uploads
are not supported.

The server independently checks that the order item belongs to the authenticated
buyer and that its seller order is `COMPLETED`. A unique constraint on the order item
prevents duplicate reviews even if concurrent submissions race. Saving a review,
updating the product's rating average/count and notifying its seller happen in the
same transaction. Only the product's seller can post or update a reply. A successful
seller reply also notifies the buyer in the same transaction, with a product link;
replies to the same review reuse one notification event key.

## Notification flow

Notifications are private to their recipient and are available from the shared
**Notifications** navigation link at `/notifications`.

- A seller receives one notification for each new seller order created at checkout.
- The buyer receives one notification after each successful seller-order transition
  in the US14 flow (`PENDING` → `PROCESSING` → `SHIPPED` → `COMPLETED`, or
  `PENDING` → `CANCELLED`).
- A seller receives a notification when a buyer submits a verified review.
- Event keys are unique, and each notification is inserted in the same transaction as
  the order/review event. A failed or retried transaction cannot leave a duplicate.
- The center displays the newest 100 notifications and the total unread count. A
  recipient can mark their own notification as read; other accounts cannot access it.

## API

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/products/{productCode}/reviews` | Public | Aggregate and latest reviews |
| `GET` | `/api/v1/products/{productCode}/reviewable-items` | Buyer | Eligible completed order items |
| `POST` | `/api/v1/products/{productCode}/reviews` | Buyer | Submit one verified-purchase review |
| `PATCH` | `/api/v1/seller/reviews/{reviewId}/reply` | Seller | Create or update the seller reply |
| `GET` | `/api/v1/notifications` | Authenticated | List own notifications and unread count |
| `PATCH` | `/api/v1/notifications/{notificationId}/read` | Authenticated | Mark own notification as read |

SQLite startup migration adds `product_metadata.review_count` to existing databases
and preserves it when rebuilding the metadata table. New review and notification
tables are created through the normal model registration path.

## Verification

Focused tests:

```powershell
python -m pytest tests/test_us15_reviews_notifications.py tests/test_seller_orders.py tests/test_checkout.py -q
```

Full suite:

```powershell
python -m pytest -v
```
