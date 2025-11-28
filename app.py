import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev_key_secret')

# Database Config
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'babytracker.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login_page'


# --- MODELS ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(200))


class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(50))  # sleep, waking, feed, growth, note (dagboek)
    subtype = db.Column(db.String(50))  # bottle, breast, solid, night_wake, day, night, diary
    value = db.Column(db.Float, nullable=True)
    value_secondary = db.Column(db.Float, nullable=True)
    start_time = db.Column(db.DateTime, default=datetime.now)
    end_time = db.Column(db.DateTime, nullable=True)
    note = db.Column(db.String(1000), nullable=True)  # Iets groter voor dagboek

    def to_dict(self):
        return {
            'id': self.id,
            'type': self.type,
            'subtype': self.subtype,
            'value': self.value,
            'value_secondary': self.value_secondary,
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'note': self.note
        }


# --- INIT ---
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def init_db():
    with app.app_context():
        db.create_all()
        # Users uit .env
        users_to_create = [
            (os.getenv('USER1_NAME'), os.getenv('USER1_PASS')),
            (os.getenv('USER2_NAME'), os.getenv('USER2_PASS'))
        ]
        for uname, upass in users_to_create:
            if uname and upass:
                if not User.query.filter_by(username=uname).first():
                    u = User(username=uname, password=generate_password_hash(upass))
                    db.session.add(u)
        db.session.commit()


init_db()


# --- ROUTES ---

@app.route('/')
def index():
    if not current_user.is_authenticated:
        return redirect(url_for('login_page'))
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        data = request.json
        user = User.query.filter_by(username=data.get('username')).first()
        if user and check_password_hash(user.password, data.get('password')):
            login_user(user)
            return jsonify({'success': True})
        return jsonify({'success': False, 'message': 'Ongeldige gegevens'}), 401
    return render_template('index.html')


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login_page'))


# --- API ---

@app.route('/api/check_auth')
def check_auth():
    return jsonify({'authenticated': current_user.is_authenticated})


@app.route('/api/status')
@login_required
def get_status():
    # Slaap status
    last_sleep = Event.query.filter_by(type='sleep').order_by(Event.start_time.desc()).first()
    is_sleeping = last_sleep and last_sleep.end_time is None

    # Nacht wakker status
    is_night_awake = False
    awake_start = None
    if is_sleeping:
        last_waking = Event.query.filter_by(type='waking').order_by(Event.start_time.desc()).first()
        if last_waking and last_waking.end_time is None:
            is_night_awake = True
            awake_start = last_waking.start_time.isoformat()

    return jsonify({
        'is_sleeping': is_sleeping,
        'sleep_start': last_sleep.start_time.isoformat() if is_sleeping else None,
        'is_night_awake': is_night_awake,
        'awake_start': awake_start
    })


@app.route('/api/events')
@login_required
def get_events():
    # Haal recente events voor de tijdlijn (geen dagboek notities, die halen we apart of filteren we)
    # We halen alles op en filteren in de frontend, of hier limit 50
    events = Event.query.filter(Event.type != 'note').order_by(Event.start_time.desc()).limit(50).all()
    return jsonify([e.to_dict() for e in events])


@app.route('/api/notes')
@login_required
def get_notes():
    # Specifiek voor het dagboek
    notes = Event.query.filter_by(type='note').order_by(Event.start_time.desc()).limit(20).all()
    return jsonify([e.to_dict() for e in notes])


@app.route('/api/toggle_sleep', methods=['POST'])
@login_required
def toggle_sleep():
    last_sleep = Event.query.filter_by(type='sleep').order_by(Event.start_time.desc()).first()
    now = datetime.now()

    if last_sleep and last_sleep.end_time is None:
        # Wakker worden
        # Sluit eventuele open waking events
        open_waking = Event.query.filter_by(type='waking').filter(Event.end_time == None).first()
        if open_waking: open_waking.end_time = now
        last_sleep.end_time = now
    else:
        # Gaan slapen
        hour = now.hour
        subtype = 'night' if (hour >= 19 or hour < 7) else 'day'
        db.session.add(Event(type='sleep', subtype=subtype, start_time=now))

    db.session.commit()
    return jsonify({'status': 'success'})


@app.route('/api/toggle_waking', methods=['POST'])
@login_required
def toggle_waking():
    last_waking = Event.query.filter_by(type='waking').order_by(Event.start_time.desc()).first()
    now = datetime.now()
    if last_waking and last_waking.end_time is None:
        last_waking.end_time = now
    else:
        db.session.add(Event(type='waking', subtype='night_wake', start_time=now))
    db.session.commit()
    return jsonify({'status': 'success'})


@app.route('/api/add_event', methods=['POST'])
@login_required
def add_event():
    d = request.json
    dt = datetime.fromisoformat(d.get('date')) if d.get('date') else datetime.now()

    db.session.add(Event(
        type=d.get('type'),
        subtype=d.get('subtype'),
        value=d.get('value'),
        value_secondary=d.get('value_secondary'),
        start_time=dt,
        note=d.get('note')
    ))
    db.session.commit()
    return jsonify({'status': 'success'})


@app.route('/api/update_event', methods=['POST'])
@login_required
def update_event():
    d = request.json
    event = Event.query.get(d.get('id'))
    if event:
        if d.get('start_time'): event.start_time = datetime.fromisoformat(d.get('start_time'))
        if d.get('end_time'):   event.end_time = datetime.fromisoformat(d.get('end_time')) if d.get(
            'end_time') else None
        if d.get('value'):      event.value = d.get('value')
        if d.get('note') is not None: event.note = d.get('note')
        db.session.commit()
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error'}), 404


@app.route('/api/delete/<int:id>', methods=['DELETE'])
@login_required
def delete_event(id):
    Event.query.filter_by(id=id).delete()
    db.session.commit()
    return jsonify({'status': 'success'})


@app.route('/api/stats')
@login_required
def get_stats():
    now = datetime.now()
    week_ago = now - timedelta(days=7)

    # Slaap Data (Uren)
    sleeps = Event.query.filter(Event.type == 'sleep', Event.start_time >= week_ago).all()
    day_hours = 0
    night_hours = 0
    for s in sleeps:
        end = s.end_time if s.end_time else now
        duration = (end - s.start_time).total_seconds() / 3600
        if s.subtype == 'day':
            day_hours += duration
        else:
            night_hours += duration

    # Voeding Data (Tellingen)
    feeds = Event.query.filter(Event.type == 'feed', Event.start_time >= week_ago).all()
    feed_counts = {'bottle': 0, 'solid': 0, 'breast': 0}
    for f in feeds:
        if f.subtype in feed_counts: feed_counts[f.subtype] += 1

    # Groei Data (Verloop)
    growth = Event.query.filter_by(type='growth').order_by(Event.start_time).all()

    return jsonify({
        'sleep_dist': [round(day_hours, 1), round(night_hours, 1)],
        'feed_dist': [feed_counts['bottle'] + feed_counts['breast'], feed_counts['solid']],
        'growth': [{'date': e.start_time.strftime('%d-%m'), 'weight': e.value} for e in growth if e.value]
    })


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)