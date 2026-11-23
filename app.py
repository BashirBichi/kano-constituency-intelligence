from __future__ import annotations

import csv
import io
import os
from datetime import datetime, timezone
from functools import wraps
from typing import Any

from flask import Flask, Response, abort, flash, redirect, render_template, request, url_for
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import func, or_
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv("SECRET_KEY", "dev-only-change-me"),
    SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL", "sqlite:///kci_dev.db").replace("postgres://", "postgresql://", 1),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "false").lower() == "true",
    WTF_CSRF_TIME_LIMIT=None,
)
db = SQLAlchemy(app)
csrf = CSRFProtect(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message_category = "warning"

ROLES = {"admin", "analyst", "field_agent", "viewer"}
CATEGORIES = ["Education", "Healthcare", "Infrastructure", "Agriculture", "Water", "Security", "Markets", "Other"]


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(30), nullable=False, default="analyst")
    active = db.Column(db.Boolean, nullable=False, default=True)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Observation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    category = db.Column(db.String(50), nullable=False, index=True)
    lga = db.Column(db.String(100), nullable=False, index=True)
    ward = db.Column(db.String(120), nullable=False, index=True)
    description = db.Column(db.Text, nullable=False)
    source_name = db.Column(db.String(180), nullable=False)
    source_type = db.Column(db.String(60), nullable=False, default="Field observation")
    evidence_url = db.Column(db.String(500))
    status = db.Column(db.String(30), nullable=False, default="pending", index=True)
    observed_on = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    verified_by = db.Column(db.Integer, db.ForeignKey("user.id"))
    verified_at = db.Column(db.DateTime(timezone=True))


@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    return db.session.get(User, int(user_id))


def role_required(*allowed: str):
    def decorator(fn):
        @wraps(fn)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role not in allowed:
                abort(403)
            return fn(*args, **kwargs)
        return wrapped
    return decorator


@app.context_processor
def inject_globals() -> dict[str, Any]:
    return {"categories": CATEGORIES}


@app.get("/")
def home():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return render_template("home.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = db.session.scalar(db.select(User).where(User.email == email, User.active.is_(True)))
        if user and user.check_password(password):
            login_user(user)
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Invalid email or password.", "danger")
    return render_template("login.html")


@app.post("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("home"))


@app.get("/dashboard")
@login_required
def dashboard():
    total = db.session.scalar(db.select(func.count(Observation.id))) or 0
    verified = db.session.scalar(db.select(func.count(Observation.id)).where(Observation.status == "verified")) or 0
    pending = db.session.scalar(db.select(func.count(Observation.id)).where(Observation.status == "pending")) or 0
    rejected = db.session.scalar(db.select(func.count(Observation.id)).where(Observation.status == "rejected")) or 0
    category_rows = db.session.execute(
        db.select(Observation.category, func.count(Observation.id))
        .group_by(Observation.category).order_by(func.count(Observation.id).desc())
    ).all()
    lga_rows = db.session.execute(
        db.select(Observation.lga, func.count(Observation.id))
        .group_by(Observation.lga).order_by(func.count(Observation.id).desc()).limit(8)
    ).all()
    recent = db.session.scalars(db.select(Observation).order_by(Observation.created_at.desc()).limit(8)).all()
    return render_template(
        "dashboard.html", total=total, verified=verified, pending=pending, rejected=rejected,
        category_labels=[r[0] for r in category_rows], category_values=[r[1] for r in category_rows],
        lga_labels=[r[0] for r in lga_rows], lga_values=[r[1] for r in lga_rows], recent=recent,
    )


@app.get("/observations")
@login_required
def observations():
    query = db.select(Observation).order_by(Observation.created_at.desc())
    search = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()
    category = request.args.get("category", "").strip()
    if search:
        pattern = f"%{search}%"
        query = query.where(or_(Observation.title.ilike(pattern), Observation.lga.ilike(pattern),
                                Observation.ward.ilike(pattern), Observation.description.ilike(pattern)))
    if status in {"pending", "verified", "rejected"}:
        query = query.where(Observation.status == status)
    if category in CATEGORIES:
        query = query.where(Observation.category == category)
    rows = db.session.scalars(query.limit(250)).all()
    return render_template("observations.html", rows=rows, search=search, selected_status=status, selected_category=category)


@app.route("/observations/new", methods=["GET", "POST"])
@role_required("admin", "analyst", "field_agent")
def new_observation():
    if request.method == "POST":
        required = ["title", "category", "lga", "ward", "description", "source_name", "observed_on"]
        values = {key: request.form.get(key, "").strip() for key in required}
        if any(not value for value in values.values()) or values["category"] not in CATEGORIES:
            flash("Complete all required fields with a valid category.", "danger")
            return render_template("observation_form.html")
        try:
            observed_on = datetime.strptime(values["observed_on"], "%Y-%m-%d").date()
        except ValueError:
            flash("Enter a valid observation date.", "danger")
            return render_template("observation_form.html")
        item = Observation(
            title=values["title"][:180], category=values["category"], lga=values["lga"][:100],
            ward=values["ward"][:120], description=values["description"], source_name=values["source_name"][:180],
            source_type=request.form.get("source_type", "Field observation")[:60],
            evidence_url=request.form.get("evidence_url", "").strip()[:500] or None,
            observed_on=observed_on, created_by=current_user.id, status="pending",
        )
        db.session.add(item)
        db.session.commit()
        flash("Observation submitted for verification.", "success")
        return redirect(url_for("observations"))
    return render_template("observation_form.html")


@app.post("/observations/<int:observation_id>/verify")
@role_required("admin", "analyst")
def verify_observation(observation_id: int):
    item = db.get_or_404(Observation, observation_id)
    action = request.form.get("action")
    if action not in {"verified", "rejected"}:
        abort(400)
    item.status = action
    item.verified_by = current_user.id
    item.verified_at = datetime.now(timezone.utc)
    db.session.commit()
    flash(f"Record marked {action}.", "success")
    return redirect(request.referrer or url_for("observations"))


@app.get("/export/observations.csv")
@role_required("admin", "analyst")
def export_observations():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Title", "Category", "LGA", "Ward", "Description", "Source", "Source Type",
                     "Evidence URL", "Status", "Observed On", "Created At"])
    rows = db.session.scalars(db.select(Observation).order_by(Observation.created_at.desc())).all()
    for item in rows:
        writer.writerow([item.id, item.title, item.category, item.lga, item.ward, item.description,
                         item.source_name, item.source_type, item.evidence_url or "", item.status,
                         item.observed_on.isoformat(), item.created_at.isoformat()])
    return Response(output.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=kci-observations.csv"})


@app.cli.command("init-db")
def init_db() -> None:
    db.create_all()
    print("Database tables created.")


@app.cli.command("seed-demo")
def seed_demo() -> None:
    db.create_all()
    if not db.session.scalar(db.select(User.id).limit(1)):
        admin = User(name="Demo Analyst", email="demo@kci.local", role="admin")
        admin.set_password(os.getenv("DEMO_PASSWORD", "ChangeMe-123!"))
        db.session.add(admin)
        db.session.flush()
        demo_rows = [
            ("Primary school classroom needs repairs", "Education", "Nassarawa", "Gama", "Community representatives reported damaged classroom roofing requiring inspection.", "Ward field visit", "Field observation", "pending"),
            ("Primary healthcare centre staffing", "Healthcare", "Gwale", "Goron Dutse", "A community discussion identified concerns about staffing levels at the local facility.", "Community meeting", "Community interview", "verified"),
            ("Feeder road condition assessment", "Infrastructure", "Dala", "Kofar Ruwa", "Residents reported difficult access during the rainy season; independent inspection is still required.", "Resident interview", "Community interview", "pending"),
            ("Seasonal produce market access", "Agriculture", "Kumbotso", "Challawa", "Traders described transport and market access constraints affecting produce movement.", "Market observation", "Market observation", "verified"),
            ("Water point functionality", "Water", "Tarauni", "Unguwa Uku", "A sample water point was reported non-functional and requires a follow-up visit.", "Ward field visit", "Field observation", "rejected"),
        ]
        for title, category, lga, ward, desc, source, source_type, status in demo_rows:
            db.session.add(Observation(title=title, category=category, lga=lga, ward=ward, description=desc,
                source_name=source, source_type=source_type, status=status,
                observed_on=datetime.now(timezone.utc).date(), created_by=admin.id,
                verified_by=admin.id if status != "pending" else None))
        db.session.commit()
        print("Demo account: demo@kci.local. Set DEMO_PASSWORD before seeding in production.")
    else:
        print("Database already contains users; demo seed skipped.")


@app.errorhandler(403)
def forbidden(_error):
    return render_template("error.html", code=403, message="You do not have permission to access this action."), 403


@app.errorhandler(404)
def not_found(_error):
    return render_template("error.html", code=404, message="The requested page was not found."), 404


with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
