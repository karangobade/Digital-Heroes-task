# Task B — Inherit and Improve: Assessment

Inherited codebase profile: no tests, business logic inside route handlers,
direct DB calls from frontend, secrets committed to repo. Live, can't go down.

## Fix order and risk of leaving each in place

| # | Issue | Risk if left | Why this order |
|---|---|---|---|
| 1 | Secrets in repo | Highest — credential leak is an active, exploitable security hole the moment the repo is cloned anywhere. Rotate immediately, this is not a refactor, it's an incident. | Fix before anything else touches the code, because every other change needs a safe place to load config from. |
| 2 | Direct DB calls from frontend | High — frontend holds DB credentials or an open query path, meaning any client-side bug or compromise is a direct data breach vector. | Fixed second because it's a security boundary, not just style. |
| 3 | No tests | High, compounding — every subsequent fix is a guess without tests. Bugs ship silently. | Add a thin test harness around current behavior *before* refactoring logic, so refactors have a safety net. |
| 4 | Business logic in route handlers | Medium — makes the code hard to change safely and blocks reuse (e.g., the same logic needed by a cron job or CLI), but doesn't fail today. | Fixed last because it's the most invasive change and the previous three make it safe to do. |

## Migration plan — no big-bang rewrite

**Week 1**
- Rotate all leaked secrets; move to environment variables / a secrets
  manager. Add `.env.example` and confirm `.gitignore` covers real `.env`.
- Add a minimal CI pipeline that runs whatever tests exist (even zero) so
  the bar can only go up from here.
- Write "characterization tests" — tests that lock in *current* behavior
  of the top 3 most-hit endpoints, bugs and all, so refactors have a
  regression net immediately.

**Month 1**
- Put an API layer (even a thin one) between frontend and DB; frontend
  stops holding credentials or building raw queries.
- Extract business logic out of the busiest 2–3 route handlers into
  plain functions/service modules, backed by the characterization tests
  from week 1. Each extraction ships as its own small, reviewable PR.
- Get real test coverage on any endpoint touched during month 1 (not
  everything — everything touched).

**Quarter 1**
- Repeat the extraction pattern across the remaining route handlers,
  prioritized by change frequency (the code people touch most is where
  the "no tests" pain shows up fastest).
- Introduce a lightweight service/repository layer convention so new
  code has an obvious place to go instead of defaulting back into route
  handlers.
- Retire the last direct-DB-from-frontend paths once the API layer covers
  100% of what the frontend needs.

The rule throughout: nothing ships as "stop the world and rewrite X" —
every step is additive or extractive, and the live service never has a
period where old and new logic can't both be reverted independently.
