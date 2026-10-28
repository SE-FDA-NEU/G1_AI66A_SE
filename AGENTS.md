# Course-aligned development guidance

The user requested that future work follow the supplied Software Engineering
slides. Apply the relevant principles below to each task; examples/homework in
the slides are reference material, not authorization to add unrelated features.

## Scope and traceability

- Read the assigned task and its parent acceptance criteria. List what already
  exists, implement only the missing assigned slice, and state exclusions.
- Keep requirement -> API/data contract -> implementation -> tests traceable.
  Update the relevant contract and traceability docs when behavior changes.
- Separate implementation completion from human review, user validation, CI and
  merge. Do not mark those steps complete without actual evidence.

## Design and code

- Keep a structured monolith. For new backend logic, dependencies run downward:
  API/controller -> service -> repository -> models/database. Controllers handle
  HTTP; services enforce rules; repositories run queries. Avoid circular imports.
- Follow existing architecture at integration boundaries; improve touched code
  in small steps rather than rewriting unrelated legacy routes.
- Use domain names, small functions with one responsibility, guard clauses,
  named limits and constants, and shared rules instead of duplicated logic.
  Comments explain why. Avoid generic dumping-ground utility modules.
- Keep business validation/authorization on the server. Derive identity from
  authenticated users, scope data reads by ownership, and use parameterized ORM
  queries. Do not expose secrets or unnecessary private data.
- Keep transaction ownership explicit. Helpers must not independently commit
  parts of one business operation. Preserve snapshots and historical facts;
  never invent missing historical data during migrations.
- Make migrations repeatable and non-destructive. Use project-relative paths,
  environment settings and existing pinned dependencies. Do not introduce
  services, frameworks or deployment work unless the assigned issue needs them.

## Testing and verification

- Derive expected results from requirements, not current output. Write a failing
  regression before fixing a behavioral bug where practical (red/green/refactor).
- Use Arrange/Act/Assert and clear test names. Prefer fast service tests, with
  integration tests for persistence/permissions/transactions and a few E2E checks.
- Cover valid/invalid partitions, below/on/above meaningful limits, and decision
  tables for combinations of rules. Prioritize money, ownership and data loss.
- Test that rejected/failed operations leave no partial writes. Use isolated
  fixtures, deterministic clocks and fake data; never production databases.
- Run relevant checks before/after small refactors. Report actual commands,
  results and limits; passing tests do not prove the absence of every bug.

## UI, collaboration and delivery

- Preserve loading/data/empty/error states; give actionable feedback and retain
  user input on errors. Confirm destructive actions against current data.
- Use consistent terms, accessible labels, visible keyboard focus, text in
  addition to color, readable mobile layouts and adequate touch targets.
- Keep commits meaningful and atomic, with issue/story references. Keep PRs
  focused, request teammate review, and declare AI assistance and verification.
  The author must be able to explain every submitted change.
- Never invent interviews, five-user tests, external reviews, CI results or a
  clean-clone run. Do not commit secrets, local databases or environment files.

## Source map

The user supplied the PDFs in the parent directory (not copied into this repo).
Page numbers below are PDF page indices starting at 1, not printed slide counters.

| Material | Principles applied |
|---|---|
| `1.pdf`, pp. 11, 16-24, 29 | Software includes docs/data; lifecycle and measurable ISO/IEC 25010:2023 quality tradeoffs |
| `week02.pdf`, pp. 18, 27, 35-39 | AI disclosure, accountable authorship, atomic commits, review and secrets |
| `week03.pdf`, pp. 7, 14-19, 27-33 | Specification/development/validation/evolution, incremental and risk-driven work, reuse |
| `week04 (2).pdf`, pp. 19, 30-32, 46-50 | Definition of Done, XP, scoped backlog tasks and traceable work |
| `week05.pdf`, pp. 9-10, 24-32 | Verifiable FR/NFR, Given/When/Then, unhappy paths, INVEST and scope |
| `week06.pdf`, pp. 7, 15, 20-26, 38 | Useful UML sketches, system boundary, sequence/error flows |
| `week07-08.pdf`, pp. 9-13, 17, 21-25, 27-38 | Constraints, layers, one-way dependencies, API/error contracts and ADRs |
| `week09.pdf`, pp. 9-19, 25-30 | Nielsen heuristics, four states, error recovery, accessibility and honest user validation |
| `week10.pdf`, pp. 7-14, 18-25, 34, 39-41 | Clean code, DRY, small refactors with safety nets, layers and AI review |
| `week11.pdf`, pp. 6-16, 22-30 | Test pyramid, partitions, boundaries, decision tables, AAA, TDD and regressions |
| `week12.pdf`, pp. 19, 24, 29, 32-36 | Reproducible dependencies, secrets/configuration and a structured monolith |
