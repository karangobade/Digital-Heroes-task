import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import app as flask_app  # noqa: E402
from models import Lead, User, db  # noqa: E402


@pytest.fixture
def app():
    flask_app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        WTF_CSRF_ENABLED=False,
    )
    with flask_app.app_context():
        db.create_all()

        admin = User(name="Admin", email="admin@test.com", role="admin")
        admin.set_password("pass1234")
        member = User(name="Member One", email="member1@test.com", role="member")
        member.set_password("pass1234")
        member2 = User(name="Member Two", email="member2@test.com", role="member")
        member2.set_password("pass1234")
        db.session.add_all([admin, member, member2])
        db.session.commit()

        lead = Lead(full_name="Test Lead", email="lead@test.com", status="new",
                    assigned_to_id=member.id)
        db.session.add(lead)
        db.session.commit()

        yield flask_app

        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, email, password="pass1234"):
    return client.post("/login", data={"email": email, "password": password}, follow_redirects=True)


# ---------------------------------------------------------------------------
# Auth rule tests
# ---------------------------------------------------------------------------

def test_public_capture_form_requires_no_auth(client):
    res = client.post("/api/leads", json={"full_name": "New Person", "email": "new@example.com"})
    assert res.status_code == 201
    assert res.get_json()["status"] == "new"


def test_capture_rejects_missing_fields(client):
    res = client.post("/api/leads", json={"full_name": "Missing Email"})
    assert res.status_code == 400


def test_api_list_requires_login(client):
    res = client.get("/api/leads")
    assert res.status_code == 302  # redirected to login by flask-login


def test_member_cannot_view_unassigned_lead(client, app):
    with app.app_context():
        other_lead = Lead(full_name="Other", email="other@test.com", status="new")
        db.session.add(other_lead)
        db.session.commit()
        other_lead_id = other_lead.id

    login(client, "member1@test.com")
    res = client.get(f"/api/leads/{other_lead_id}")
    assert res.status_code == 403


def test_member_can_view_own_assigned_lead(client, app):
    with app.app_context():
        lead = Lead.query.filter_by(email="lead@test.com").first()
        lead_id = lead.id

    login(client, "member1@test.com")
    res = client.get(f"/api/leads/{lead_id}")
    assert res.status_code == 200
    assert res.get_json()["email"] == "lead@test.com"


def test_admin_can_view_any_lead(client, app):
    with app.app_context():
        lead = Lead.query.filter_by(email="lead@test.com").first()
        lead_id = lead.id

    login(client, "admin@test.com")
    res = client.get(f"/api/leads/{lead_id}")
    assert res.status_code == 200


def test_member_cannot_reassign_lead(client, app):
    with app.app_context():
        lead = Lead.query.filter_by(email="lead@test.com").first()
        lead_id = lead.id
        member2 = User.query.filter_by(email="member2@test.com").first()
        member2_id = member2.id

    login(client, "member1@test.com")
    res = client.patch(f"/api/leads/{lead_id}", json={"assigned_to_id": member2_id})
    assert res.status_code == 403


def test_admin_can_reassign_lead(client, app):
    with app.app_context():
        lead = Lead.query.filter_by(email="lead@test.com").first()
        lead_id = lead.id
        member2 = User.query.filter_by(email="member2@test.com").first()
        member2_id = member2.id

    login(client, "admin@test.com")
    res = client.patch(f"/api/leads/{lead_id}", json={"assigned_to_id": member2_id})
    assert res.status_code == 200
    assert res.get_json()["assigned_to"]["id"] == member2_id


# ---------------------------------------------------------------------------
# Core flow tests
# ---------------------------------------------------------------------------

def test_full_lead_lifecycle_flow(client, app):
    """Capture -> assign (admin) -> status update (member) -> note -> activity trail."""
    # 1. Public capture
    res = client.post("/api/leads", json={"full_name": "Flow Test", "email": "flow@test.com"})
    lead_id = res.get_json()["id"]

    with app.app_context():
        member = User.query.filter_by(email="member1@test.com").first()
        member_id = member.id

    # 2. Admin assigns it
    login(client, "admin@test.com")
    res = client.patch(f"/api/leads/{lead_id}", json={"assigned_to_id": member_id})
    assert res.status_code == 200
    client.get("/logout")

    # 3. Member updates status
    login(client, "member1@test.com")
    res = client.patch(f"/api/leads/{lead_id}", json={"status": "contacted"})
    assert res.status_code == 200
    assert res.get_json()["status"] == "contacted"

    # 4. Member adds a note
    res = client.post(f"/api/leads/{lead_id}/notes", json={"body": "Called, left voicemail."})
    assert res.status_code == 201

    # 5. Activity trail reflects all of it
    res = client.get(f"/api/leads/{lead_id}")
    activity_actions = [a["action"] for a in res.get_json()["activity"]]
    assert "created" in activity_actions
    assert "assigned" in activity_actions
    assert "status_changed" in activity_actions
    assert "note_added" in activity_actions


def test_pagination_and_status_filter(client, app):
    with app.app_context():
        for i in range(5):
            db.session.add(Lead(full_name=f"Bulk {i}", email=f"bulk{i}@test.com", status="qualified"))
        db.session.commit()

    login(client, "admin@test.com")
    res = client.get("/api/leads?status=qualified&page=1&per_page=3")
    body = res.get_json()
    assert res.status_code == 200
    assert len(body["data"]) == 3
    assert body["pagination"]["total"] == 5
    assert body["pagination"]["total_pages"] == 2


def test_invalid_status_filter_returns_400(client):
    login(client, "admin@test.com")
    res = client.get("/api/leads?status=not_a_real_status")
    assert res.status_code == 400
