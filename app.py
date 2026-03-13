import hashlib
import os
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, jsonify, request, send_from_directory, session

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # Optional for local SQLite-only runs
    psycopg = None
    dict_row = None

ROOT = Path(__file__).parent
PUBLIC_DIR = ROOT / 'public'
DB_PATH = ROOT / 'cleaning.db'
DATABASE_URL = os.environ.get('DATABASE_URL', '')

WEEKLY_SECTIONS = {
    'Daily': [
        'Make Bed', 'Empty Trash', 'Do Dishes', 'Clean & Sweep Kitchen',
        'One load of laundry', 'Sanitize countertops', 'Sort mails',
        'Wipe down surfaces', 'Sweep or Vacuum'
    ],
    'Monday': [
        'Clean sink', 'Clean Stovetop', 'Clean Kitchen Table', 'Wipe Appliances',
        'Wipe Fridge', 'Sweep & Mop', 'Clean and Dry Dish Rack', 'Sanitize Surfaces'
    ],
    'Tuesday': [
        'Vacuum & Mop Floor', 'Clean Electronics', 'Dust & Wipe Furniture', 'Declutter',
        'Spot Clean Stains', 'Arrange Furniture', 'Organize Books/magazines', 'Check lightening'
    ],
    'Wednesday': [
        'Vacuum & Mop Floor', 'Change sheets', 'Dust & Wipe Furniture', 'Declutter',
        'Tidy clothes & drawer', 'Spot Clean Stains', 'Air Purification', 'Organize Clothing'
    ],
    'Thursday': [
        'Wipe Mirrors', 'Clean toilet, bath & sink', 'Vacuum & Mop Floor', 'Stock up Toilet paper',
        'Replace towels & Rugs', 'Empty Trash', 'Clean Mirrors', 'Check for Spills'
    ],
    'Friday': [
        'Change Rugs', 'Organize shoes/coats', 'Disinfect Doorknobs', 'Dust Surfaces',
        'Dust Decorations', 'Clean Glass Surfaces', 'Shake Out Mats', 'Check for Spills'
    ],
    'Saturday': [
        'Clean out Fridge', 'Organize Pantry', 'Clear Expired Items', 'Plan Your Meals',
        'Make a Shopping List', 'Grocery shopping', 'Unload and Organize'
    ],
    'Sunday': [
        'Vacuum Car', 'Clean Blinds', 'Clean Hallways', 'Pet Hair Removal',
        'Clean Under Furniture', 'Declutter Drawers', 'Dryer Vent Cleaning', 'Carpet & Rug Cleaning'
    ]
}

MONTHLY = [
    'Wipe Kitchen Cabinets', 'Clean Microwave, Oven, Toaster', 'Deep Clean Fridge',
    'Disinfect Trash cans', 'Clean Laundry room', 'Clean below Furniture',
    'organize Drawers', 'Wash Duvets & Blankets'
]

ANNUAL = [
    ('J', 'Declutter & Clean storage rooms'), ('F', 'Deep clean outdoors'), ('M', 'Deep clean floors'),
    ('A', 'Dust & Wipe Light Fixtures'), ('M', 'Clear Garage'), ('J', 'Clean Shed'), ('J', 'Clean Gutters'),
    ('A', 'Wash Rugs'), ('S', 'organize Kitchen cabinets'), ('O', 'Sort unused clothes & donate/sell'),
    ('N', 'Wash Windows'), ('D', 'Inspect and Replace Batteries')
]


class DB:
    def __init__(self):
        self.is_postgres = DATABASE_URL.startswith('postgres://') or DATABASE_URL.startswith('postgresql://')
        if self.is_postgres and psycopg is None:
            raise RuntimeError('DATABASE_URL is set to Postgres but psycopg is not installed.')

    def connect(self):
        if self.is_postgres:
            return psycopg.connect(DATABASE_URL, row_factory=dict_row)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def q(self, sql):
        return sql.replace('?', '%s') if self.is_postgres else sql


db = DB()
_db_initialized = False


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 200000)
    return f"{salt}${digest.hex()}"


def verify_password(password, encoded):
    salt, _ = encoded.split('$', 1)
    return hash_password(password, salt) == encoded


def init_db():
    global _db_initialized
    if _db_initialized:
        return

    with db.connect() as conn:
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
              username TEXT UNIQUE NOT NULL,
              password_hash TEXT NOT NULL,
              created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''' if db.is_postgres else '''
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              username TEXT UNIQUE NOT NULL,
              password_hash TEXT NOT NULL,
              created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
              id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
              section TEXT NOT NULL,
              frequency TEXT NOT NULL,
              label TEXT NOT NULL,
              sort_order INTEGER NOT NULL,
              UNIQUE(section, label)
            )
        ''' if db.is_postgres else '''
            CREATE TABLE IF NOT EXISTS tasks (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              section TEXT NOT NULL,
              frequency TEXT NOT NULL,
              label TEXT NOT NULL,
              sort_order INTEGER NOT NULL,
              UNIQUE(section, label)
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS completions (
              id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
              user_id INTEGER NOT NULL,
              task_id INTEGER NOT NULL,
              week_start TEXT NOT NULL,
              completed INTEGER NOT NULL DEFAULT 0,
              updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
              UNIQUE(user_id, task_id, week_start)
            )
        ''' if db.is_postgres else '''
            CREATE TABLE IF NOT EXISTS completions (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL,
              task_id INTEGER NOT NULL,
              week_start TEXT NOT NULL,
              completed INTEGER NOT NULL DEFAULT 0,
              updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
              UNIQUE(user_id, task_id, week_start)
            )
        ''')

        cur.execute('SELECT COUNT(*) AS count FROM tasks')
        count_row = cur.fetchone()
        count = count_row['count'] if db.is_postgres else count_row[0]
        if count == 0:
            for section, labels in WEEKLY_SECTIONS.items():
                for idx, label in enumerate(labels):
                    cur.execute(db.q('INSERT INTO tasks(section, frequency, label, sort_order) VALUES (?, ?, ?, ?)'),
                                (section, 'weekly', label, idx))
            for idx, label in enumerate(MONTHLY):
                cur.execute(db.q('INSERT INTO tasks(section, frequency, label, sort_order) VALUES (?, ?, ?, ?)'),
                            ('Monthly', 'monthly', label, idx))
            for idx, (month, label) in enumerate(ANNUAL):
                cur.execute(db.q('INSERT INTO tasks(section, frequency, label, sort_order) VALUES (?, ?, ?, ?)'),
                            (f'Annual {month}', 'annual', label, idx))
        conn.commit()

    _db_initialized = True


app = Flask(__name__, static_folder=str(PUBLIC_DIR), static_url_path='')
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-me')


@app.get('/api/auth/me')
def auth_me():
    init_db()
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'user': None})

    with db.connect() as conn:
        cur = conn.cursor()
        cur.execute(db.q('SELECT id, username FROM users WHERE id = ?'), (user_id,))
        user = cur.fetchone()
    return jsonify({'user': dict(user) if user else None})


@app.get('/api/tasks')
def get_tasks():
    init_db()
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    with db.connect() as conn:
        cur = conn.cursor()
        cur.execute('SELECT id, section, frequency, label, sort_order FROM tasks ORDER BY id')
        rows = cur.fetchall()
    return jsonify({'tasks': [dict(r) for r in rows]})


@app.get('/api/completions')
def get_completions():
    init_db()
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    week = request.args.get('weekStart')
    if not week:
        return jsonify({'error': 'weekStart query required'}), 400

    with db.connect() as conn:
        cur = conn.cursor()
        cur.execute(db.q('SELECT task_id, completed FROM completions WHERE user_id = ? AND week_start = ?'), (user_id, week))
        rows = cur.fetchall()
    return jsonify({'completions': {r['task_id']: bool(r['completed']) for r in rows}})


@app.post('/api/auth/register')
def register():
    init_db()
    body = request.get_json(silent=True) or {}
    username = (body.get('username') or '').strip()
    password = body.get('password') or ''

    if not username or len(password) < 6:
        return jsonify({'error': 'Provide username and password (6+ chars).'}), 400

    with db.connect() as conn:
        cur = conn.cursor()
        try:
            if db.is_postgres:
                cur.execute(
                    'INSERT INTO users(username, password_hash) VALUES (%s, %s) RETURNING id',
                    (username, hash_password(password))
                )
                user_id = cur.fetchone()['id']
            else:
                cur.execute('INSERT INTO users(username, password_hash) VALUES (?, ?)',
                            (username, hash_password(password)))
                user_id = cur.lastrowid
            conn.commit()
        except Exception as exc:
            if 'UNIQUE' in str(exc).upper() or 'duplicate key' in str(exc).lower():
                return jsonify({'error': 'Username already exists.'}), 409
            raise

    session['user_id'] = user_id
    return jsonify({'id': user_id, 'username': username})


@app.post('/api/auth/login')
def login():
    init_db()
    body = request.get_json(silent=True) or {}
    username = (body.get('username') or '').strip()
    password = body.get('password') or ''

    with db.connect() as conn:
        cur = conn.cursor()
        cur.execute(db.q('SELECT id, username, password_hash FROM users WHERE username = ?'), (username,))
        user = cur.fetchone()

    if not user or not verify_password(password, user['password_hash']):
        return jsonify({'error': 'Invalid credentials.'}), 401

    session['user_id'] = user['id']
    return jsonify({'id': user['id'], 'username': user['username']})


@app.post('/api/auth/logout')
def logout():
    session.pop('user_id', None)
    return jsonify({'ok': True})


@app.post('/api/completions')
def set_completion():
    init_db()
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    body = request.get_json(silent=True) or {}
    week = body.get('weekStart')
    task_id = body.get('taskId')
    completed = body.get('completed')

    if not week or not isinstance(task_id, int) or not isinstance(completed, bool):
        return jsonify({'error': 'Invalid payload'}), 400

    with db.connect() as conn:
        cur = conn.cursor()
        cur.execute(db.q('''
            INSERT INTO completions(user_id, task_id, week_start, completed, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, task_id, week_start)
            DO UPDATE SET completed=excluded.completed, updated_at=excluded.updated_at
        '''), (user_id, task_id, week, int(completed), datetime.utcnow().isoformat()))
        conn.commit()

    return jsonify({'ok': True})


@app.get('/')
def root_index():
    return send_from_directory(PUBLIC_DIR, 'index.html')


@app.get('/<path:path>')
def static_files(path):
    file_path = PUBLIC_DIR / path
    if file_path.exists() and file_path.is_file():
        return send_from_directory(PUBLIC_DIR, path)
    return send_from_directory(PUBLIC_DIR, 'index.html')


def main():
    parsed = urlparse(DATABASE_URL)
    if DATABASE_URL and parsed.scheme.startswith('postgres'):
        print('Using Postgres database (e.g., Neon).')
    else:
        print(f'Using SQLite database at {DB_PATH}.')

    init_db()
    port = int(os.environ.get('PORT', '3000'))
    app.run(host='0.0.0.0', port=port, debug=False)


if __name__ == '__main__':
    main()
