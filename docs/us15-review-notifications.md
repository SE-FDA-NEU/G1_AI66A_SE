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
1 to 5, an optional comment, and up to five absolute HTTP(S) media URLs, one per
line. File uploads are not supported. Images and supported video URLs have inline
previews with links; unsupported formats or failed previews retain an open-media
link. Comments and replies are rendered as text.

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

## Product-detail UI follow-up (#131)

Existing work from #130 supplies eligibility/ownership/uniqueness checks, rating
aggregates and seller-reply endpoints. This task completes their presentation on
`/products/{productCode}`: rating/count summaries, per-review ratings/comments,
image/video references, seller replies and their timestamps where available.
It retains the existing design and adds loading, data, empty and recoverable error
states, including a reviews Retry button and bounded network waits.

Only an authenticated buyer with a completed, unreviewed purchase sees an enabled
review form. Rating, comment length and media URLs have associated error messages
and focus moves to the first invalid control. A failed request retains the draft;
a successful submission refreshes the summary and eligibility while keeping the
success message visible outside the hidden form. Submission locks prevent duplicate
clicks. Account changes and logout invalidate the previous account's form/response.
Owning sellers have labelled reply controls with validation, draft recovery and
save feedback; other sellers have none. Reply times use API UTC timestamps and
are displayed in the viewer's local time. Missing timestamps are omitted.

### Minimal media persistence extension

The #130 API had only `media_url`; #131 explicitly requires `images_json`, so this
branch adds that storage/read bridge without changing review authorization,
aggregate calculations or notification behavior (#132).

- `POST /api/v1/products/{productCode}/reviews` accepts optional `media_urls`, a
  list of at most 5 absolute HTTP(S) URLs, each at most 2048 characters. Comment
  length remains 2000 and rating remains an integer from 1 to 5.
- The existing `media_url` input/output remains supported. New clients send
  `media_urls`; existing clients can still read the first attachment via
  `media_url`. Combined legacy/new inputs cannot exceed the five-reference limit.
- URL references are deduplicated and serialized in `reviews.images_json` inside
  the existing review transaction. Public review and seller-reply responses return
  the normalized `media_urls` collection and UTC creation/reply timestamps.
- Startup migration adds the column once and copies each old `media_url` into its
  collection. Re-running migration does not overwrite current media collections
  or rewrite legacy review/comment facts.
- The browser previews common image extensions and MP4/WebM/Ogg video URLs using
  native controls. It never auto-plays video or inserts review data as HTML. Other
  URLs remain ordinary links; network/codec failures show a fallback link. The
  server stores references and does not download, host or transcode attachments.

### Evidence and reproduction

```powershell
python -m pytest tests/test_review_media.py tests/test_us15_reviews_notifications.py tests/test_product_detail.py tests/test_database.py tests/test_ui_docs_contract.py -q
node tests/product_detail_ui.mjs
node tests/product_detail_variants.mjs
node tests/reviews_browser.mjs
python -m ruff check src tests/test_review_media.py
```

`reviews_browser.mjs` uses installed Chrome/Edge and deterministic API fixtures
with the production HTML/CSS/JavaScript. It checks 390/768/1280px layouts, overflow,
media fallback, timestamps, validation focus, failed-save draft recovery, successful
submission, seller replies and retry. Actual persistence/validation/migration is
verified separately by the Python tests. These checks do not claim five-user
validation, external review, CI success or a clean-clone run.

The subsequent [Request Changes verification for #131](evidence/issue131-verification.md)
records the actual CI run for the reviewed commit, a new Python 3.12 clone/setup,
and real-server persistence and Chrome checks separately from those fixtures.

Screenshots: [mobile](images/us15/reviews-390.png),
[tablet](images/us15/reviews-768.png), [desktop](images/us15/reviews-1280.png),
[validation](images/us15/review-validation-390.png),
[seller reply](images/us15/seller-reply-1280.png).

AI assistance: OpenAI Codex assisted with issue/source inspection, implementation,
regressions and browser evidence. Human review remains a separate delivery step.

## Verification

Focused tests:

```powershell
python -m pytest tests/test_us15_reviews_notifications.py tests/test_seller_orders.py tests/test_checkout.py -q
```

Full suite:

```powershell
python -m pytest -v
```
