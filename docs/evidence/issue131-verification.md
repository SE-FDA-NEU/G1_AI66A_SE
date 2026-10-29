# Issue #131: Request Changes verification

Verified on 2026-10-29 for [PR #190](https://github.com/SE-FDA-NEU/G1_AI66A_SE/pull/190),
implementation commit `8f03a2fc23765ea6ddc6b17ff3952864635a20a7` on
`feat/131-product-reviews-ui`. The review requested CI, clean-clone startup and
migration/review regression evidence. It did not request a behavior change.

## CI on the reviewed commit

[Pull-request CI run 40817950974](https://github.com/SE-FDA-NEU/G1_AI66A_SE/actions/runs/40817950974)
completed successfully on 2026-10-29 at 04:32:40 UTC. The run reports the same
commit above and uses Ubuntu with Python 3.12.

| Check | Observed result |
|---|---|
| Full Python suite | **842 passed, 1 warning**, 197.44 seconds |
| `tests/test_review_media.py` | All 13 cases passed, including repeatable legacy migration, media persistence/validation and reply timestamps |
| `tests/test_us15_reviews_notifications.py` | All 13 cases passed, including purchase ownership/eligibility, aggregate updates, seller authorization and notification compatibility |
| Page script checks | All eight CI scripts passed, including product-detail eligibility, media, validation, retries, drafts and account isolation |
| Dependency installation, lint and secret checks | Successful |

The separate Node build job was skipped because this repository has no
`package.json`; the page scripts ran inside the Python job. The existing workflow
makes lint non-blocking, although this run's lint step itself succeeded.
[Push CI run 40817855603](https://github.com/SE-FDA-NEU/G1_AI66A_SE/actions/runs/40817855603)
also succeeded for this commit. These links describe the reviewed implementation,
not any later commit that adds this evidence document.

Inspect the immutable run and individual migration/review cases with:

```powershell
gh run view 40817950974 --repo SE-FDA-NEU/G1_AI66A_SE
gh run view 40817950974 --repo SE-FDA-NEU/G1_AI66A_SE --log |
    Select-String 'test_review_media.py::|test_us15_reviews_notifications.py::|842 passed'
```

## Clean-clone setup

A new clone was downloaded from the remote branch into a temporary directory on
Windows. It reused no working-tree files, virtual environment or existing database.
A separate CPython **3.12.16** interpreter created its virtual environment; the
existing workspace interpreter was Python 3.11 and was not used for this check.
The setup followed [README Quickstart](../../README.md#quickstart) and
[SETUP](../SETUP.md), using `requirements.txt` without an extra runtime dependency.

The following commands summarize the executed setup, with Python 3.12 selected
before creating the environment:

```powershell
git clone --branch feat/131-product-reviews-ui --single-branch https://github.com/SE-FDA-NEU/G1_AI66A_SE.git
cd G1_AI66A_SE
git rev-parse HEAD
python --version
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip check
Copy-Item .env.example .env
$env:DEBUG = 'false'
$env:APP_ENV = 'development'
$env:DATABASE_URL = 'sqlite:///./marketplace.db'
python -m src.database
python -m src.seed
python -m src.seed
python -m src.database
python -m src.main
```

The implementation SHA was checked before execution. Pip was **26.2.2** and
`pip check` printed `No broken requirements found.` Initialization completed
successfully. The first seed reported **Added: 45 / Total: 45 / Active: 45**;
the second reported **Added: 0 / Total: 45 / Active: 45**. Repeating initialization
also succeeded.

The first initialization attempt encountered an inherited shell variable
`DEBUG=release`, which is not a valid boolean. Explicitly setting the documented
`DEBUG=false` resolved it. SETUP section 3 already documents that shell values
override `.env`; no application validation or committed configuration was changed.

## Running application and persistence checks

`python -m src.main` served the fresh clone at `http://127.0.0.1:8000`. HTTP checks
against that running server, using only the documented seeded development
accounts, verified:

1. `/health` reported `ok` and `database: connected`. The catalog API returned
   20 of 45 products, starting with `P-100`. `/products`, `/products/P-100`,
   `/docs`, product-detail JavaScript and review CSS returned HTTP 200.
2. The buyer added `P-100` to the cart and checked out. Its seller confirmed,
   shipped and delivered the order; the buyer confirmed receipt. The completed
   order item became eligible for review.
3. The buyer submitted a five-star review with an image reference to the app's
   `/static/product-placeholder.svg`. HTTP 201 returned the media collection;
   a separate SQLite read confirmed that `reviews.images_json` stored it.
4. The owning seller saved a reply. The public review API returned that reply,
   `rating: 5.0`, `review_count: 1`, and a UTC `seller_replied_at` value ending
   in `Z`. The observed timestamp was `2026-10-29T05:22:45.793440Z`.
5. A duplicate review returned HTTP 409; the purchase no longer appeared among
   eligible review items and the database still contained one review.

An isolated headless Chrome profile then loaded the production product page with
the real server/database, without API fixtures. At 390px it displayed Wireless
Mouse, the verified-purchase summary, image and seller reply. The reply's HTML
`time` retained its UTC value, the guest review form was hidden, the login prompt
was visible and the page had no horizontal document overflow. The captured
[running-app screenshot](../images/us15/clean-clone-131.png) was visually inspected.
This complements the fixture-driven UI checks recorded in the
[US15 contract](../us15-review-notifications.md#evidence-and-reproduction).

The temporary server and browser were stopped after verification. No development
database, `.env`, authentication token or browser profile is included in this PR.

## Local regressions

The clean environment also passed:

```powershell
node tests/product_detail_ui.mjs
node tests/product_detail_variants.mjs
python -m ruff check src tests/test_review_media.py
```

The first full-suite attempt in the restricted execution environment encountered
Windows `PermissionError: [WinError 5]` while accessing pytest's `.pytest_temp`
directory. The full suite was rerun outside that restriction with a new temporary
base directory:

```powershell
python -m pytest -q --basetemp=../pytest-rerun --junitxml=../clean-clone-rerun.xml
```

Result: **839 passed, 1 skipped, 1 warning in 322.41 seconds**, exit code 0.
Both review test files passed all 13 cases each, including the legacy migration.
The skipped item is collection of `tests/test_catalog_browser.py`: Playwright is
not in the README `requirements.txt` installation. CI installs it separately and
ran the three additional browser cases, producing the 842-test result above.
The warning is Starlette's existing `httpx` TestClient deprecation. No dependency
or source change was made to suppress the warning or skip a failing test.

## Delivery boundaries

These are AI-assisted checks performed on the author's Windows machine, plus the
linked GitHub Actions results. They do not establish independent teammate review,
a fresh-machine run by another person, five-user usability validation or approval.
Reviewer approval and merging remain separate steps. Notification UI work (#132)
and unrelated features are outside this verification change.
