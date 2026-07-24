# Lead Platform

A small lead-management app a sales team could actually use — not a lead form,
a full lifecycle tool: capture, assignment, status pipeline, notes, and an
activity trail, sitting behind role-based auth (admin / member).

Built for the Digital Heroes Full Stack Development task (Task A).

## Stack and why

- **Flask** — the brief asked for a coherent full-stack app, not a
  microservice; Flask + Jinja lets the same codebase serve both the UI and
  the JSON API without a separate frontend build step, which keeps this
  small app auditable in one sitting.
- **SQLAlchemy + SQLite** — relational data (leads → notes → activity,
  users → assignments) fits a relational model better than a document store.
  SQLite for local/demo simplicity; swapping `DATABASE_URL` to Postgres is a
  one-line change since nothing here is SQLite-specific.
- **Flask-Login** for session auth — simpler than JWT for a
  server-rendered app where the browser already holds a session cookie;
  the JSON API reuses the same session, so there's one auth system, not two.
- **Server-side permission checks on every API route** — the UI hides
  admin-only controls, but that's cosmetic. Every state-changing endpoint
  re-checks `current_user` role and lead ownership independently, because a
  user can always call the API directly, bypassing the UI.

## Roles and permissions

| Action | Member | Admin |
|---|---|---|
| View leads assigned to them | ✅ | ✅ (all leads) |
| View leads assigned to someone else | ❌ (403) | ✅ |
| Update status of their own lead | ✅ | ✅ (any lead) |
| Reassign a lead | ❌ (403) | ✅ |
| Add a note to their own lead | ✅ | ✅ (any lead) |

## Setup

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

flask --app app.py seed           # creates leads.db + demo users/leads
flask --app app.py run            # http://127.0.0.1:5000
```

Demo accounts (created by `seed`):

| Email | Password | Role |
|---|---|---|
| admin@digitalheroes.test | Admin@12345 | admin |
| ravi@digitalheroes.test | Member@12345 | member |

Public capture form: `/capture` (no login needed).

## Running tests

```bash
python3 -m pytest tests/ -v
```

11 tests covering: public capture validation, auth-required routes, a
member blocked from viewing/reassigning a lead they don't own, an admin
allowed to do both, the full lifecycle flow (capture → assign → status
update → note → activity trail all recorded), pagination, and status-filter
validation.

## API contract

All endpoints return JSON. Authenticated endpoints require an active
session cookie (log in via `/login` first).

### `POST /api/leads` — public, no auth

Create a lead (used by the public capture form).

```json
// Request
{ "full_name": "Priya Shah", "email": "priya@example.com", "phone": "9876543210",
  "company": "Shah Retail", "message": "Interested in Shopify migration" }

// 201 Created
{ "id": 3, "status": "new", "assigned_to": null, "created_at": "...", ... }
```

- `400` if `full_name` or `email` missing.

### `GET /api/leads` — auth required

List leads. Members only ever see their own; admins see all.

Query params: `page` (default 1), `per_page` (default 20, max 100),
`status` (one of `new/contacted/qualified/won/lost`), `assigned_to`
(admins only, unless filtering to themselves).

```json
{
  "data": [ { "id": 1, "full_name": "...", "status": "new", ... } ],
  "pagination": { "page": 1, "per_page": 20, "total": 2, "total_pages": 1 }
}
```

- `400` invalid `status` value or non-integer `page`/`per_page`.
- `403` member tries to filter by another user's `assigned_to`.

### `GET /api/leads/<id>` — auth required

Full lead detail including notes and activity trail.

- `404` lead doesn't exist.
- `403` member requesting a lead not assigned to them.

### `PATCH /api/leads/<id>` — auth required

Update `status` and/or `assigned_to_id`. Either or both in one call.

```json
{ "status": "contacted" }
{ "assigned_to_id": 2 }
{ "assigned_to_id": null }   // unassign
```

- `403` non-admin attempting `assigned_to_id`, or editing a lead not theirs.
- `400` invalid status value, unknown `assigned_to_id`, or no recognized
  field in the body.
- Every change is written to the activity trail.

### `POST /api/leads/<id>/notes` — auth required

```json
{ "body": "Called, left voicemail." }
```

- `403` if the lead isn't assigned to the caller (and caller isn't admin).
- `400` if `body` is empty.
- Logged to the activity trail as `note_added`.

## Assumption made

The brief didn't specify how members get access to a lead in the first
place, so I assumed **admin-only assignment**: leads start unassigned,
and only an admin routes them to a member. This mirrors how most small
sales teams actually run lead distribution and keeps a single, auditable
point of ownership change — a member picking up an unassigned lead
themselves would need a separate "claim" endpoint, which felt out of scope
for this brief.

## What I'd add for a real production deployment

- Password reset flow (currently seed-only accounts)
- Rate limiting on the public `/api/leads` POST endpoint to prevent spam
- CSRF token on the HTML forms (Flask-WTF) — currently relying on
  same-origin fetch calls only
- Structured logging with request IDs
- A proper migrations tool (Alembic) instead of `db.create_all()`

## Where I used AI

I used Claude to scaffold the Flask app structure (models, routes, and the
permission-decorator pattern) and to write the initial test skeletons, then
worked through the actual permission rules, the activity-trail design, and
the assumption about admin-only assignment myself — those are the parts an
interviewer would actually be probing, so I made sure I could defend every
one of them rather than just accepting the first version generated.
