# Technical observations and findings index (#83)

This file contains one repository/automated-test observation. It is not evidence
of three independent heuristic reviews or external-user testing. No completed
human-review finding is included. The unused form is in the separately labelled
[blank finding template](templates/finding.md).

## OBS01: browser entry returned JSON rather than the catalog

- Source: repository/HTTP inspection by Codex during #83 implementation;
  accountable owner: @minhnm162. This is an automated technical observation.
- Observed baseline: main fac5740; root handler in src/main.py.
- Reproduction: GET / with Accept: text/html.
- Before: 200 JSON status payload, without navigation into the shopping UI.
- Expected: browser entry reaches the catalog; status clients retain JSON.
- Fix: commit 0ca90fc, redirect text/html requests to /products with HTTP 307.
- Automated verification date/environment: 2026-10-18, Windows, Python 3.11.9.
- Retest: tests/test_health.py::test_browser_root_enters_catalog_without_changing_json_status
  checks redirect, successful catalog follow-up and the retained JSON response.
  tests/test_p0_flows.py::test_p0_seller_creation_to_buyer_receipt checks the
  root-to-purchase HTTP/database path. Both passed in the recorded 313-pass run.
- Evidence: executable tests and the baseline/result table in
  [Sprint 3 evidence section 4.3](../sprint3.md#43-automated-verification).
- Severity: no human usability rating assigned; the earlier proposed score was
  not an independent reviewer assessment and is not counted as one.
- Status: implemented and automatically verified. Browser/human retest has not
  been recorded as a completed session; no external-user validation is claimed.

Future observed human findings require actual source, environment, severity,
owner, evidence and retest outcome. Do not close #83 while required reviews,
sessions or severity 3-4 retests remain incomplete.
