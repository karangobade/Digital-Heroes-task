from functools import wraps

from flask import Flask, jsonify, redirect, render_template, request, url_for
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)

from config import Config
from models import ActivityLog, Lead, LEAD_STATUSES, Note, User, db

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ---------------------------------------------------------------------------
# Permission helpers
# ---------------------------------------------------------------------------

def admin_required(view_fn):
    """Server-side enforcement — never trust the frontend alone for this."""

    @wraps(view_fn)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            return jsonify({"error": "forbidden", "message": "Admin access required."}), 403
        return view_fn(*args, **kwargs)

    return wrapped


def can_view_lead(user, lead):
    return user.is_admin or lead.assigned_to_id == user.id


def can_edit_lead(user, lead):
    # Members may only work leads assigned to them; admins may edit any lead.
    return user.is_admin or lead.assigned_to_id == user.id


def log_activity(lead, actor, action, detail=None):
    db.session.add(ActivityLog(lead_id=lead.id, actor_id=actor.id if actor else None, action=action, detail=detail))


# ---------------------------------------------------------------------------
# Public pages
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return redirect(url_for("capture_form"))


@app.route("/capture", methods=["GET"])
def capture_form():
    return render_template("capture_form.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for("dashboard"))
        return render_template("login.html", error="Invalid email or password."), 401
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Authenticated pages
# ---------------------------------------------------------------------------

@app.route("/dashboard")
@login_required
def dashboard():
    query = Lead.query
    if not current_user.is_admin:
        query = query.filter_by(assigned_to_id=current_user.id)
    leads = query.order_by(Lead.created_at.desc()).all()
    members = User.query.filter_by(role="member").all() if current_user.is_admin else []
    return render_template(
        "dashboard.html", leads=leads, members=members, statuses=LEAD_STATUSES
    )


@app.route("/leads/<int:lead_id>")
@login_required
def lead_detail(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    if not can_view_lead(current_user, lead):
        return render_template("403.html"), 403
    members = User.query.filter_by(role="member").all() if current_user.is_admin else []
    notes = lead.notes.order_by(Note.created_at.desc()).all()
    activities = lead.activities.order_by(ActivityLog.created_at.desc()).all()
    return render_template(
        "lead_detail.html", lead=lead, members=members, statuses=LEAD_STATUSES,
        notes=notes, activities=activities,
    )


# ---------------------------------------------------------------------------
# JSON API
#
# Contract summary (see README for full docs):
#   POST   /api/leads              public — create a lead from the capture form
#   GET    /api/leads              auth   — list leads (paginated + filterable)
#   GET    /api/leads/<id>         auth   — lead detail incl. notes + activity trail
#   PATCH  /api/leads/<id>         auth   — update status and/or assignment
#   POST   /api/leads/<id>/notes   auth   — add a timestamped note
# ---------------------------------------------------------------------------

@app.route("/api/leads", methods=["POST"])
def api_create_lead():
    data = request.get_json(silent=True) or request.form
    full_name = (data.get("full_name") or "").strip()
    email = (data.get("email") or "").strip()

    if not full_name or not email:
        return jsonify({"error": "validation_error", "message": "full_name and email are required."}), 400

    lead = Lead(
        full_name=full_name,
        email=email,
        phone=(data.get("phone") or "").strip() or None,
        company=(data.get("company") or "").strip() or None,
        message=(data.get("message") or "").strip() or None,
        source=(data.get("source") or "web_form"),
        status="new",
    )
    db.session.add(lead)
    db.session.flush()  # get lead.id before logging
    log_activity(lead, actor=None, action="created", detail="Lead captured via public form")
    db.session.commit()

    return jsonify(lead.to_dict()), 201


@app.route("/api/leads", methods=["GET"])
@login_required
def api_list_leads():
    try:
        page = max(int(request.args.get("page", 1)), 1)
        per_page = min(max(int(request.args.get("per_page", 20)), 1), 100)
    except ValueError:
        return jsonify({"error": "validation_error", "message": "page and per_page must be integers."}), 400

    query = Lead.query
    if not current_user.is_admin:
        query = query.filter_by(assigned_to_id=current_user.id)

    status_filter = request.args.get("status")
    if status_filter:
        if status_filter not in LEAD_STATUSES:
            return jsonify({
                "error": "validation_error",
                "message": f"status must be one of {LEAD_STATUSES}.",
            }), 400
        query = query.filter_by(status=status_filter)

    assigned_to = request.args.get("assigned_to")
    if assigned_to:
        if not current_user.is_admin and str(current_user.id) != assigned_to:
            return jsonify({"error": "forbidden", "message": "Members can only filter their own leads."}), 403
        query = query.filter_by(assigned_to_id=assigned_to)

    query = query.order_by(Lead.created_at.desc())
    total = query.count()
    leads = query.offset((page - 1) * per_page).limit(per_page).all()

    return jsonify({
        "data": [l.to_dict() for l in leads],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": (total + per_page - 1) // per_page if total else 0,
        },
    }), 200


@app.route("/api/leads/<int:lead_id>", methods=["GET"])
@login_required
def api_get_lead(lead_id):
    lead = Lead.query.get(lead_id)
    if not lead:
        return jsonify({"error": "not_found", "message": "Lead does not exist."}), 404
    if not can_view_lead(current_user, lead):
        return jsonify({"error": "forbidden", "message": "You cannot view this lead."}), 403
    return jsonify(lead.to_dict(include_notes=True)), 200


@app.route("/api/leads/<int:lead_id>", methods=["PATCH"])
@login_required
def api_update_lead(lead_id):
    lead = Lead.query.get(lead_id)
    if not lead:
        return jsonify({"error": "not_found", "message": "Lead does not exist."}), 404
    if not can_edit_lead(current_user, lead):
        return jsonify({"error": "forbidden", "message": "You cannot edit this lead."}), 403

    data = request.get_json(silent=True) or {}
    changed = []

    if "status" in data:
        new_status = data["status"]
        if new_status not in LEAD_STATUSES:
            return jsonify({
                "error": "validation_error",
                "message": f"status must be one of {LEAD_STATUSES}.",
            }), 400
        if new_status != lead.status:
            log_activity(lead, current_user, "status_changed", f"{lead.status} -> {new_status}")
            lead.status = new_status
            changed.append("status")

    if "assigned_to_id" in data:
        if not current_user.is_admin:
            return jsonify({"error": "forbidden", "message": "Only admins may reassign leads."}), 403
        new_assignee_id = data["assigned_to_id"]
        if new_assignee_id is not None:
            assignee = User.query.get(new_assignee_id)
            if not assignee:
                return jsonify({"error": "validation_error", "message": "assigned_to_id does not exist."}), 400
        log_activity(lead, current_user, "assigned", f"assigned_to_id -> {new_assignee_id}")
        lead.assigned_to_id = new_assignee_id
        changed.append("assigned_to_id")

    if not changed:
        return jsonify({"error": "validation_error", "message": "No recognized fields to update."}), 400

    db.session.commit()
    return jsonify(lead.to_dict()), 200


@app.route("/api/leads/<int:lead_id>/notes", methods=["POST"])
@login_required
def api_add_note(lead_id):
    lead = Lead.query.get(lead_id)
    if not lead:
        return jsonify({"error": "not_found", "message": "Lead does not exist."}), 404
    if not can_edit_lead(current_user, lead):
        return jsonify({"error": "forbidden", "message": "You cannot add notes to this lead."}), 403

    data = request.get_json(silent=True) or {}
    body = (data.get("body") or "").strip()
    if not body:
        return jsonify({"error": "validation_error", "message": "body is required."}), 400

    note = Note(lead_id=lead.id, author_id=current_user.id, body=body)
    db.session.add(note)
    log_activity(lead, current_user, "note_added")
    db.session.commit()

    return jsonify(note.to_dict()), 201


# ---------------------------------------------------------------------------
# CLI helper: seed the database with demo users + leads
# ---------------------------------------------------------------------------

@app.cli.command("seed")
def seed():
    """flask --app app.py seed"""
    db.drop_all()
    db.create_all()

    admin = User(name="Asha Admin", email="admin@digitalheroes.test", role="admin")
    admin.set_password("Admin@12345")
    member = User(name="Ravi Member", email="ravi@digitalheroes.test", role="member")
    member.set_password("Member@12345")
    db.session.add_all([admin, member])
    db.session.flush()

    lead1 = Lead(full_name="Priya Shah", email="priya@example.com", company="Shah Retail",
                 message="Interested in Shopify migration", status="new")
    lead2 = Lead(full_name="Karan Mehta", email="karan@example.com", company="Mehta Foods",
                 message="Wants a performance marketing quote", status="contacted",
                 assigned_to_id=member.id)
    db.session.add_all([lead1, lead2])
    db.session.flush()
    log_activity(lead1, None, "created", "seed data")
    log_activity(lead2, admin, "assigned", f"assigned_to_id -> {member.id}")
    db.session.commit()
    print("Seeded: admin@digitalheroes.test / Admin@12345, ravi@digitalheroes.test / Member@12345")


if __name__ == "__main__":
    app.run(debug=True)
