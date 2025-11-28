import os
from datetime import datetime, timedelta

from dotenv import load_dotenv
from flask import Flask, send_from_directory, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    login_required,
    logout_user,
    current_user,
)
from werkzeug.security import generate_password_hash, check_password_hash

# -------------------------------------------------
# Config
# -------------------------------------------------

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev_key_secret")

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "babytracker.db")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "index"  # we doen login via de SPA

# -------------------------------------------------
# Models
# -------------------------------------------------


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

    def set_password(self, raw_password: str) -> None:
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)

    def to_dict(self) -> dict:
        return {"id": self.id, "username": self.username}


class Event(db.Model):
    __tablename__ = "events"

    id = db.Column(db.Integer, primary_key=True)
    # type: sleep, feed, diaper, growth, note
    type = db.Column(db.String(50), nullable=False)
    # extra detail: bottle / breast / solid, pee / poop / mixed, day / night, etc.
    subtype = db.Column(db.String(50), nullable=True)
    # value: bij voeding of gewicht
    value = db.Column(db.Float, nullable=True)
    # value_secondary: extra veld, bv. lengte of hoeveelheid in ml
    value_secondary = db.Column(db.Float, nullable=True)
    start_time = db.Column(db.DateTime, default=datetime.now, nullable=False)
    end_time = db.Column(db.DateTime, nullable=True)
    note = db.Column(db.String(1000), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "subtype": self.subtype,
            "value": self.value,
            "value_secondary": self.value_secondary,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "note": self.note,
        }


# -------------------------------------------------
# Helpers
# -------------------------------------------------


@login_manager.user_loader
def load_user(user_id: str):
    if not user_id:
        return None
    try:
        return User.query.get(int(user_id))
    except (TypeError, ValueError):
        return None


def init_db() -> None:
    """Maak database + standaard gebruikers uit .env aan."""
    with app.app_context():
        db.create_all()

        env_users = [
            (os.getenv("USER1_NAME"), os.getenv("USER1_PASS")),
            (os.getenv("USER2_NAME"), os.getenv("USER2_PASS")),
        ]

        for username, raw_password in env_users:
            if not username or not raw_password:
                continue

            existing = User.query.filter_by(username=username).first()
            if existing:
                continue

            u = User(username=username)
            u.set_password(raw_password)
            db.session.add(u)

        db.session.commit()


def now() -> datetime:
    return datetime.now()


def is_night(dt: datetime) -> bool:
    """Simpel onderscheid dag/nacht."""
    hour = dt.hour
    return hour < 7 or hour >= 19


# -------------------------------------------------
# Routes – frontend
# -------------------------------------------------


@app.route("/")
def index():
    # we serveren gewoon de index.html uit dezelfde map
    return send_from_directory(BASE_DIR, "index.html")


# -------------------------------------------------
# Auth API
# -------------------------------------------------


@app.route("/api/me")
def api_me():
    if current_user.is_authenticated:
        return jsonify({"authenticated": True, "user": current_user.to_dict()})
    return jsonify({"authenticated": False, "user": None})


@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username or not password:
        return jsonify({"ok": False, "error": "Gebruikersnaam en wachtwoord zijn verplicht."}), 400

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return jsonify({"ok": False, "error": "Onjuiste inloggegevens."}), 401

    login_user(user)
    return jsonify({"ok": True, "user": user.to_dict()})


@app.route("/api/logout", methods=["POST"])
@login_required
def api_logout():
    logout_user()
    return jsonify({"ok": True})


# -------------------------------------------------
# Event API – invoer
# -------------------------------------------------


@app.route("/api/sleep/toggle", methods=["POST"])
@login_required
def api_sleep_toggle():
    """Start of stop slaap. Als er een lopende slaap is -> stop, anders start."""
    now_dt = now()
    open_sleep = (
        Event.query.filter_by(type="sleep", end_time=None)
        .order_by(Event.start_time.desc())
        .first()
    )

    if open_sleep:
        open_sleep.end_time = now_dt
        db.session.commit()
        return jsonify({"ok": True, "status": "stopped", "event": open_sleep.to_dict()})

    # start nieuwe slaap
    subtype = "night" if is_night(now_dt) else "day"
    new_sleep = Event(type="sleep", subtype=subtype, start_time=now_dt)
    db.session.add(new_sleep)
    db.session.commit()
    return jsonify({"ok": True, "status": "started", "event": new_sleep.to_dict()})


@app.route("/api/feed", methods=["POST"])
@login_required
def api_feed():
    data = request.get_json(silent=True) or {}
    subtype = data.get("subtype") or "bottle"
    value = data.get("amount")
    value_secondary = data.get("duration")

    event = Event(
        type="feed",
        subtype=subtype,
        value=float(value) if value is not None else None,
        value_secondary=float(value_secondary) if value_secondary is not None else None,
        start_time=now(),
    )
    db.session.add(event)
    db.session.commit()
    return jsonify({"ok": True, "event": event.to_dict()})


@app.route("/api/diaper", methods=["POST"])
@login_required
def api_diaper():
    data = request.get_json(silent=True) or {}
    subtype = data.get("subtype") or "pee"

    event = Event(
        type="diaper",
        subtype=subtype,
        start_time=now(),
    )
    db.session.add(event)
    db.session.commit()
    return jsonify({"ok": True, "event": event.to_dict()})


@app.route("/api/growth", methods=["POST"])
@login_required
def api_growth():
    data = request.get_json(silent=True) or {}
    weight = data.get("weight")
    length = data.get("length")

    if weight is None and length is None:
        return jsonify({"ok": False, "error": "Gewicht of lengte is verplicht."}), 400

    event = Event(
        type="growth",
        subtype="measurement",
        value=float(weight) if weight is not None else None,
        value_secondary=float(length) if length is not None else None,
        start_time=now(),
    )
    db.session.add(event)
    db.session.commit()
    return jsonify({"ok": True, "event": event.to_dict()})


@app.route("/api/note", methods=["POST"])
@login_required
def api_note():
    data = request.get_json(silent=True) or {}
    text = (data.get("note") or "").strip()

    if not text:
        return jsonify({"ok": False, "error": "Notitie mag niet leeg zijn."}), 400

    event = Event(
        type="note",
        subtype="diary",
        note=text,
        start_time=now(),
    )
    db.session.add(event)
    db.session.commit()
    return jsonify({"ok": True, "event": event.to_dict()})


# -------------------------------------------------
# Event API – uitlezen
# -------------------------------------------------


@app.route("/api/events")
@login_required
def api_events():
    """Alle events van de laatste X dagen (default 2)."""
    days = request.args.get("days", default=2, type=int)
    since = now() - timedelta(days=days)

    events = (
        Event.query.filter(Event.start_time >= since)
        .order_by(Event.start_time.desc())
        .all()
    )
    return jsonify({"ok": True, "events": [e.to_dict() for e in events]})


@app.route("/api/status")
@login_required
def api_status():
    """Korte 'nu'-status voor bovenin de app."""
    # laatste slaap
    last_sleep = (
        Event.query.filter_by(type="sleep")
        .order_by(Event.start_time.desc())
        .first()
    )
    is_sleeping = bool(last_sleep and last_sleep.end_time is None)

    # laatste voeding / luier / groei
    last_feed = (
        Event.query.filter_by(type="feed")
        .order_by(Event.start_time.desc())
        .first()
    )
    last_diaper = (
        Event.query.filter_by(type="diaper")
        .order_by(Event.start_time.desc())
        .first()
    )
    last_growth = (
        Event.query.filter_by(type="growth")
        .order_by(Event.start_time.desc())
        .first()
    )

    def fmt_event(e: Event | None):
        if not e:
            return None
        return {
            "type": e.type,
            "subtype": e.subtype,
            "when": e.start_time.isoformat(),
        }

    return jsonify(
        {
            "ok": True,
            "is_sleeping": is_sleeping,
            "last_sleep_start": last_sleep.start_time.isoformat() if last_sleep else None,
            "last_feed": fmt_event(last_feed),
            "last_diaper": fmt_event(last_diaper),
            "last_growth": fmt_event(last_growth),
        }
    )


@app.route("/api/summary")
@login_required
def api_summary():
    """Data voor de grafieken (laatste 24 uur + volledige groeicurve)."""
    now_dt = now()
    since = now_dt - timedelta(hours=24)

    # Slaap (dag/nacht uren in laatste 24 uur)
    sleeps = (
        Event.query.filter_by(type="sleep")
        .filter(Event.start_time >= since)
        .all()
    )

    day_hours = 0.0
    night_hours = 0.0

    for s in sleeps:
        start = s.start_time
        end = s.end_time or now_dt
        duration = (end - start).total_seconds() / 3600.0

        # heel simpele indeling op basis van starttijd
        if is_night(start):
            night_hours += duration
        else:
            day_hours += duration

    # Voeding (aantal per soort in laatste 24 uur)
    feeds = (
        Event.query.filter_by(type="feed")
        .filter(Event.start_time >= since)
        .all()
    )
    feed_counts = {"bottle": 0, "breast": 0, "solid": 0}
    for f in feeds:
        if f.subtype in feed_counts:
            feed_counts[f.subtype] += 1

    # Groei (volledige reeks)
    growth_events = (
        Event.query.filter_by(type="growth")
        .order_by(Event.start_time.asc())
        .all()
    )

    growth_series = []
    for e in growth_events:
        if e.value is None:
            continue
        growth_series.append(
            {
                "date": e.start_time.strftime("%d-%m"),
                "weight": e.value,
            }
        )

    return jsonify(
        {
            "ok": True,
            "sleep_dist": [round(day_hours, 1), round(night_hours, 1)],
            "feed_dist": [
                feed_counts["bottle"] + feed_counts["breast"],
                feed_counts["solid"],
            ],
            "growth": growth_series,
        }
    )


# -------------------------------------------------
# Entrypoint
# -------------------------------------------------


if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="0.0.0.0", port=5000)
