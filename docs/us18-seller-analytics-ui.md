# US18 seller analytics UI (#143)

## Assigned boundary

Task #143 implements the charts, summary, date/group filters and best-selling
ranking from story #110. The existing seller-only API already supplies completed
item revenue, time buckets and a units-based ranking. This change adds the browser
page at `/seller/analytics`; `/seller/analytics/products` opens the same dashboard
and focuses the ranking heading once the report loads. Applying filters afterwards
keeps the user's focus rather than jumping back to the heading.
Links from seller orders and product management make it discoverable.

Financial aggregation and its persistence tests belong to #142. Low-stock alerts
and variant thresholds belong to #144. This task changes no order, payment,
escrow, pricing, database or migration behavior. It adds no chart dependency.

## API and display contract

The page verifies `/api/v1/auth/me` before requesting private data. The API remains
responsible for seller authorization and ownership. No seller ID comes from the
browser. Guests and expired sessions go to login with a return path; buyers see an
access explanation. Changing accounts clears the old report before reloading.

| View | Request | Response used |
|---|---|---|
| Summary and time series | `GET /api/v1/seller/analytics` with `from_date`, `to_date`, `group_by=day\|month` and matching legacy `from`, `to`, `period=daily\|monthly` | `data[].period` and the four financial fields; aggregate fields from `meta` |
| Best sellers | `GET /api/v1/seller/analytics/best-sellers` with the same `from`, `to`, `sort_by=units`, `limit=5\|10\|20` | `product_id`, `product_code`, `product_name`, `units_sold`, `revenue` |

Defaults are the last 30 UTC calendar days, inclusive, grouped by day, with ten
best sellers. Dates must exist and From must not exceed To. The UI deliberately
offers day/month only, as required by #110; the older API's weekly option remains
available to other clients. Monthly grouping can make a longer range easier to read.

The four cards are separately labelled `gross_order_value`, `completed_revenue`,
`pending_escrow_revenue` (integer VND) and `cancellation_rate` (percentage). Values
come from the API, including the aggregate cancellation rate: the UI neither
averages bucket rates nor multiplies an already-percent value by 100. Financial
metrics under the #142 contract use order creation dates. Completed-product sales
use completion dates and historical item prices. Ranking is units descending;
equal returned quantities use product ID ascending for stable display. `units_sold`
is the current API's name for the story's sold-count measure.

### Compatibility with the existing backend

Before #142 is integrated, the API returns `meta.total_revenue` and
`data[].revenue`, but not the four new financial fields. The page explicitly labels
this fallback **Completed-sales revenue (legacy)**, explains its completion-date
basis and shows **Not available** for absent metrics. It never invents gross value,
escrow or cancellation rates from completed-only sales. Selecting an unavailable
metric shows an explanation instead of a zero-valued chart. This fallback is
usable, but does not establish completion of #110's new financial API acceptance.

The older US09/US10 planning documents remain historical. This scoped contract
defines the implemented date defaults, grouping choices, metric distinctions and
shared route behavior for #143.

## Interaction and accessibility

Both endpoints must succeed for the captured filter range before the report is
shown. Loading and failure hide previous values; Retry uses the failed applied
filters while preserving any unapplied form edits. Invalid filters receive linked
field errors and keyboard focus. Superseded requests and old-account responses
cannot overwrite a newer report or log out the new session. Requests have bounded
deadlines, and malformed financial values produce an actionable error.

The native SVG chart supports selecting each metric without another API call.
Its accessible title and description identify the metric/unit, and an expandable
table supplies exact values. Missing or all-zero series have a useful explanation;
an empty ranking independently explains that there are no completed-product sales.
Amounts use VND formatting; percentages keep their own unit. Names and messages
are inserted as text. Narrow screens contain chart/table scrolling inside their
panels, with visible instructions, labelled fields and keyboard focus indicators.

## Verification and evidence

The single test matrix and runnable commands are maintained in
[testing.md](testing.md#task-143-seller-analytics-charts-and-ranking).
The native-browser checks use deterministic API fixtures for both current and
#142 response shapes; they do not prove persistence or a merged #142 integration.
Python regressions exercise the existing real API and served page assets.

Fixture screenshots: [phone](images/us18/analytics-390.png),
[tablet](images/us18/analytics-768.png), [desktop](images/us18/analytics-1280.png),
[invalid filters](images/us18/analytics-validation-390.png),
[empty report](images/us18/analytics-empty-390.png),
[current API fallback](images/us18/analytics-legacy-390.png).
Automated checks do not substitute for teammate review, human usability testing,
required CI checks or merge approval.
