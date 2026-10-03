# Definition of Done

A story is Done when **all** of the following are true. Not "mostly true".
If one box is unticked, the story stays in the sprint and carries over.

| # | Criterion | Who checks |
|---|-----------|------------|
| 1 | Every acceptance criterion on the issue passes | Reviewer, by hand |
| 2 | The feature works from a clean clone with only the README steps | Reviewer |
| 3 | At least one automated test covers the new behaviour | CI |
| 4 | CI is green on the PR branch | CI |
| 5 | Code reviewed and approved by a teammate who did not write it | GitHub |
| 6 | Merged into `main` | GitHub |
| 7 | No secrets, `.env`, or database dumps in the diff | CI |
| 8 | `docs/traceability.md` updated if a screen or route changed | Reviewer |

## What Done is not

- "It works on my machine" - criterion 2 exists for this reason.
- "I will write the test later." Later is Sprint 4, and Sprint 4 is the demo.
- "My teammate approved it in five seconds." A review with no comments on a
  300-line PR is not a review. Ask a real question.

## Changing this document

The team may add criteria at a retrospective. Removing one requires the
lecturer's agreement, and the reason goes in the retro notes.
