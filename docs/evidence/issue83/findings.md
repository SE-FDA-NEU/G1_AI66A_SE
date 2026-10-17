# Findings and retest register (#83)

Technical observations are separate from the three human heuristic reviews.
No real-user finding or independent-review completion is claimed here.

| ID | Source | Finding | Severity | Owner | Status | Evidence / retest |
|---|---|---|---|---|---|---|
| OBS01 | Repository/HTTP inspection by implementation agent | Browser opening / gets status JSON, with no entry into the shopping UI | Proposed 3 (human triage pending) | @minhnm162 | Fixed in working tree; automated retest passes; browser retest pending | Root now redirects text/html requests to /products; API clients retain JSON. test_p0_seller_creation_to_buyer_receipt and existing test_root_endpoint |

## New finding template

- ID / source reviewer or anonymous participant: pending
- Commit, route and environment: pending
- Steps, expected and actual result: pending
- Evidence: pending
- Severity 0-4 and impact/rationale: pending
- Owner: pending
- Fix commit/PR: pending
- Retest tester/date/commit, same steps and result: pending
- Evidence after fix / remaining issue: pending

Do not close observed severity 3-4 issues based solely on a fix description. Run the
same scenario after the fix and record the outcome, including human retest when the
finding is about usability. All findings, including deferred severity 1-2, retain owners.
