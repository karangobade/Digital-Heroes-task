from datetime import datetime

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()

LEAD_STATUSES = ["new", "contacted", "qualified", "won", "lost"]
ROLES = ["admin", "member"]


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="member")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    assigned_leads = db.relationship("Lead", backref="assignee", foreign_keys="Lead.assigned_to_id")

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)

    @property
    def is_admin(self):
        return self.role == "admin"

    def to_dict(self):
        return {"id": self.id, "name": self.name, "email": self.email, "role": self.role}


class Lead(db.Model):
    __tablename__ = "leads"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30))
    company = db.Column(db.String(120))
    message = db.Column(db.Text)
    source = db.Column(db.String(50), default="web_form")

    status = db.Column(db.String(20), nullable=False, default="new")
    assigned_to_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    notes = db.relationship("Note", backref="lead", cascade="all, delete-orphan", lazy="dynamic")
    activities = db.relationship("ActivityLog", backref="lead", cascade="all, delete-orphan", lazy="dynamic")

    def to_dict(self, include_notes=False):
        data = {
            "id": self.id,
            "full_name": self.full_name,
            "email": self.email,
            "phone": self.phone,
            "company": self.company,
            "message": self.message,
            "source": self.source,
            "status": self.status,
            "assigned_to": self.assignee.to_dict() if self.assignee else None,
            "created_at": self.created_at.isoformat() + "Z",
            "updated_at": self.updated_at.isoformat() + "Z",
        }
        if include_notes:
            data["notes"] = [n.to_dict() for n in self.notes.order_by(Note.created_at.desc())]
            data["activity"] = [a.to_dict() for a in self.activities.order_by(ActivityLog.created_at.desc())]
        return data


class Note(db.Model):
    __tablename__ = "notes"

    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id"), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    author = db.relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "body": self.body,
            "author": self.author.name if self.author else None,
            "created_at": self.created_at.isoformat() + "Z",
        }


class ActivityLog(db.Model):
    """Append-only trail: who changed what on a lead, and when."""

    __tablename__ = "activity_logs"

    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id"), nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(50), nullable=False)  # e.g. "status_changed", "assigned", "note_added"
    detail = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    actor = db.relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "action": self.action,
            "detail": self.detail,
            "actor": self.actor.name if self.actor else "system",
            "created_at": self.created_at.isoformat() + "Z",
        }
