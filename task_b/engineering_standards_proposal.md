# Task B — Engineering Standards Proposal

## Standards to introduce

1. **No business logic in route/controller handlers.** Handlers do:
   auth check → parse input → call a service function → shape response.
   Anything else (calculations, side effects, cross-entity rules) lives in
   a plain function the handler calls.
2. **All queries go through the ORM / a data-access layer** — no raw SQL
   string building anywhere in request-handling code.
3. **Every state-changing endpoint requires a test** before merge: one
   happy path, one permission-denied path.
4. **Secrets never touch the repo** — config via environment variables,
   `.env.example` committed, real `.env` gitignored, checked by a
   pre-commit hook that scans for common credential patterns.
5. **Every mutation that changes a record's state writes an audit trail
   entry** (who, what, when) — non-negotiable for anything customer-facing.

## Getting a resistant team to adopt this

- **Don't start with a rewrite mandate.** Start with the pre-commit
  secret-scanner and the CI test gate — both are invisible until someone
  breaks the rule, so they don't feel like extra work for people already
  writing decent code.
- **Ship the first extraction myself, as a small PR, on the highest-traffic
  endpoint** — a working example beats a style guide. Reference it in the
  standards doc so "look at PR #X" is a real answer to "why though."
- **Make the new pattern the path of least resistance**, not just the
  documented one: a code-generation snippet or a copy-pasteable service
  template so following the standard is faster than not.
- **Review, don't gatekeep, existing code** — the standard applies to new
  and touched code, not a retroactive rewrite demand on everything the
  team already shipped. That's what keeps the migration plan realistic
  and keeps the team from feeling punished for past decisions made under
  different constraints.
