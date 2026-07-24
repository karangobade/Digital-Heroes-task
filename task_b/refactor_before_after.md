# Task B — Refactor Demo: Before / After

A realistic bad sample in the style described in the brief: business logic
buried in the route handler, direct SQL string building, no separation
between validation, persistence, and response shaping.

## Before

```python
@app.route("/api/leads/<int:lead_id>", methods=["POST"])
def update_lead(lead_id):
    data = request.get_json()
    conn = sqlite3.connect("leads.db")
    cur = conn.cursor()

    # business logic + validation + persistence all inline
    cur.execute("SELECT * FROM leads WHERE id=%s" % lead_id)  # SQL injection risk
    lead = cur.fetchone()
    if lead is None:
        return "not found", 404

    if data.get("status"):
        if data["status"] not in ["new", "contacted", "qualified", "won", "lost"]:
            return "bad status", 400
        cur.execute(
            "UPDATE leads SET status='%s' WHERE id=%s" % (data["status"], lead_id)
        )
        # no activity log — no record of who changed what, when
        if data["status"] == "won":
            # business rule buried three levels deep, untested
            cur.execute("UPDATE users SET deals_won = deals_won + 1 WHERE id=%s" % lead["assigned_to"])

    conn.commit()
    conn.close()
    return "ok"
```

**Problems:** string-formatted SQL (injection), no input model, no
permission check at all, silent business rule (`deals_won` counter) with
no test and no audit trail, inconsistent response format (`"ok"` instead
of JSON + status code), connection opened/closed by hand every request.

## After

```python
# models.py — parameterized ORM queries, no raw SQL string building
def transition_lead_status(lead: Lead, new_status: str, actor: User) -> None:
    """Single place that owns what happens when a lead's status changes."""
    if new_status not in LEAD_STATUSES:
        raise ValueError(f"status must be one of {LEAD_STATUSES}")

    previous_status = lead.status
    lead.status = new_status
    db.session.add(ActivityLog(
        lead_id=lead.id, actor_id=actor.id,
        action="status_changed", detail=f"{previous_status} -> {new_status}",
    ))

    if new_status == "won" and lead.assignee:
        lead.assignee.deals_won = (lead.assignee.deals_won or 0) + 1


# app.py — route handler only orchestrates: auth, call, respond
@app.route("/api/leads/<int:lead_id>", methods=["PATCH"])
@login_required
def api_update_lead(lead_id):
    lead = Lead.query.get(lead_id)
    if not lead:
        return jsonify({"error": "not_found"}), 404
    if not can_edit_lead(current_user, lead):
        return jsonify({"error": "forbidden"}), 403

    data = request.get_json(silent=True) or {}
    if "status" in data:
        try:
            transition_lead_status(lead, data["status"], current_user)
        except ValueError as e:
            return jsonify({"error": "validation_error", "message": str(e)}), 400

    db.session.commit()
    return jsonify(lead.to_dict()), 200
```

## What improved

- **No SQL injection surface** — the ORM parameterizes everything.
- **The "won" business rule is named, testable, and in one place** —
  `transition_lead_status` can be unit-tested directly without spinning up
  the whole HTTP stack.
- **Every status change is now audited** via `ActivityLog`, which the old
  version silently dropped.
- **Permission check happens before any state change**, not never.
- **Consistent JSON responses with real status codes**, so a frontend or
  API consumer can actually branch on the result.
- **The route handler is now ~10 lines of orchestration** — auth, fetch,
  delegate, respond — which is exactly the shape that makes it easy to
  add a second entry point (e.g. a CLI or a scheduled job) later without
  duplicating the business rule.
