# Sprint 2 Evidence

This document records the repository evidence used to verify the Sprint 2 administrative requirements.

## Sprint 2 summary

| Item | Result |
|---|---|
| Sprint dates | 2026-09-21 to 2026-10-04 |
| Product Owner | `@leducminh290506-eng` |
| Scrum Master | `@minhnm162` |
| Sprint 1 Scrum Master | `@leducminh290506-eng` |
| Scrum Master rotation | PASS |

## Closed issues

| Issue | Title | Status |
|---|---|---|
| #43 | Define system architecture and ADRs | Closed |
| #44 | Design relational database schema and ERD | Closed |
| #45 | Story: view products from the database | Closed |
| #46 | Implement database schema and seed dataset | Closed |
| #47 | Define REST API contract | Closed |
| #48 | Implement application database connection | Closed |
| #49 | Implement GET /products using real database data | Closed |
| #50 | Complete Sprint 2 system design documentation | Closed |
| #51 | Create fresh-machine setup guide | Closed |
| #52 | Verify setup on a non-author machine | Closed |
| #53 | Update traceability and implementation evidence | Closed |
| #56 | Bootstrap runnable application skeleton | Closed |

## Merged pull requests

| PR | Purpose | Reviewed by another member |
|---|---|---|
| #58 | Database/backend work | Yes |
| #59 | Database implementation | Yes |
| #60 | `/products` page | Yes |
| #61 | Walking skeleton cleanup/evidence | Yes |
| #64 | Independent verification | Yes |
| #65 | Schema/database integration | Yes |


## Walking skeleton verification

The implemented path is:

```text
Browser
→ /products
→ GET /api/v1/products
→ FastAPI
→ SQLModel / SQLAlchemy
→ SQLite
→ JSON response
→ browser product cards