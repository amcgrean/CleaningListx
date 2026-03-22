import hashlib
import os
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, jsonify, request, send_from_directory, session
import jwt

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
NEON_AUTH_ISSUER = os.environ.get('NEON_AUTH_ISSUER', '')
NEON_AUTH_AUDIENCE = os.environ.get('NEON_AUTH_AUDIENCE', '')
NEON_AUTH_JWKS_URL = os.environ.get('NEON_AUTH_JWKS_URL', '')

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

VALID_SECTIONS = (
    ['Daily', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday', 'Monthly'] +
    [f'Annual {i}' for i in range(1, 13)]
)


def get_frequency_for_section(section):
    if section.startswith('Annual'):
        return 'annual'
    if section == 'Monthly':
        return 'monthly'
    return 'weekly'


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
_jwks_client = None


def neon_auth_enabled():
    return bool(NEON_AUTH_ISSUER and NEON_AUTH_JWKS_URL)


def get_jwks_client():
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(NEON_AUTH_JWKS_URL)
    return _jwks_client


def extract_neon_user():
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.lower().startswith('bearer '):
        return None

    token = auth_header.split(' ', 1)[1].strip()
    if not token:
        return None

    try:
        signing_key = get_jwks_client().get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=['RS256'],
            issuer=NEON_AUTH_ISSUER,
            audience=NEON_AUTH_AUDIENCE or None,
            options={'verify_aud': bool(NEON_AUTH_AUDIENCE)}
        )
    except Exception:
        return None

    return {
        'external_id': payload.get('sub'),
        'username': payload.get('email') or payload.get('preferred_username') or payload.get('sub')
    }


def current_user_id():
    if not neon_auth_enabled():
        return session.get('user_id')

    neon_user = extract_neon_user()
    if not neon_user or not neon_user['external_id']:
        return None

    with db.connect() as conn:
        cur = conn.cursor()
        cur.execute(db.q('SELECT id FROM users WHERE external_id = ?'), (neon_user['external_id'],))
        row = cur.fetchone()
        if row:
            return row['id']

        if db.is_postgres:
            cur.execute(
                'INSERT INTO users(username, password_hash, external_id) VALUES (%s, %s, %s) RETURNING id',
                (neon_user['username'], '', neon_user['external_id'])
            )
            user_id = cur.fetchone()['id']
        else:
            cur.execute(
                'INSERT INTO users(username, password_hash, external_id) VALUES (?, ?, ?)',
                (neon_user['username'], '', neon_user['external_id'])
            )
            user_id = cur.lastrowid
        conn.commit()
        return user_id


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
              external_id TEXT UNIQUE,
              created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''' if db.is_postgres else '''
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              username TEXT UNIQUE NOT NULL,
              password_hash TEXT NOT NULL,
              external_id TEXT UNIQUE,
              created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        if db.is_postgres:
            cur.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS external_id TEXT UNIQUE')
        else:
            cur.execute('PRAGMA table_info(users)')
            columns = [r['name'] for r in cur.fetchall()]
            if 'external_id' not in columns:
                cur.execute('ALTER TABLE users ADD COLUMN external_id TEXT')
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

        cur.execute('''
            CREATE TABLE IF NOT EXISTS households (
              id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
              name TEXT NOT NULL,
              invite_code TEXT UNIQUE NOT NULL,
              created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''' if db.is_postgres else '''
            CREATE TABLE IF NOT EXISTS households (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL,
              invite_code TEXT UNIQUE NOT NULL,
              created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS household_members (
              id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
              household_id INTEGER NOT NULL,
              user_id INTEGER NOT NULL UNIQUE,
              role TEXT NOT NULL DEFAULT 'member',
              joined_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''' if db.is_postgres else '''
            CREATE TABLE IF NOT EXISTS household_members (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              household_id INTEGER NOT NULL,
              user_id INTEGER NOT NULL UNIQUE,
              role TEXT NOT NULL DEFAULT 'member',
              joined_at TEXT DEFAULT CURRENT_TIMESTAMP
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
                            (f'Annual {idx + 1}', 'annual', label, idx))
        conn.commit()

        # Migrate annual sections from letter format (e.g. "Annual J") to number format (e.g. "Annual 1")
        cur.execute(db.q("SELECT id, section, sort_order FROM tasks WHERE frequency = 'annual' ORDER BY sort_order"))
        annual_rows = cur.fetchall()
        needs_migration = any(not row['section'].replace('Annual ', '').isdigit() for row in annual_rows)
        if needs_migration:
            for row in annual_rows:
                if not row['section'].replace('Annual ', '').isdigit():
                    month_num = min(max(row['sort_order'] + 1, 1), 12)
                    cur.execute(db.q('UPDATE tasks SET section = ? WHERE id = ?'), (f'Annual {month_num}', row['id']))
            conn.commit()

    _db_initialized = True


app = Flask(__name__, static_folder=str(PUBLIC_DIR), static_url_path='')
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-me')


@app.get('/api/auth/me')
def auth_me():
    init_db()
    user_id = current_user_id()
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
    user_id = current_user_id()
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
    user_id = current_user_id()
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
    if neon_auth_enabled():
        return jsonify({'error': 'Registration is managed by Neon Auth.'}), 400
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
    if neon_auth_enabled():
        return jsonify({'error': 'Login is managed by Neon Auth. Include a Bearer token in API requests.'}), 400
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
    if neon_auth_enabled():
        return jsonify({'ok': True})
    session.pop('user_id', None)
    return jsonify({'ok': True})


@app.get('/api/auth/config')
def auth_config():
    return jsonify({'provider': 'neon' if neon_auth_enabled() else 'local'})


@app.post('/api/completions')
def set_completion():
    init_db()
    user_id = current_user_id()
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


@app.get('/api/household')
def get_household():
    init_db()
    user_id = current_user_id()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    with db.connect() as conn:
        cur = conn.cursor()
        cur.execute(db.q('''
            SELECT h.id, h.name, h.invite_code, hm.role
            FROM household_members hm
            JOIN households h ON h.id = hm.household_id
            WHERE hm.user_id = ?
        '''), (user_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({'household': None})

        household = dict(row)
        cur.execute(db.q('''
            SELECT u.id, u.username, hm.role
            FROM household_members hm
            JOIN users u ON u.id = hm.user_id
            WHERE hm.household_id = ?
            ORDER BY hm.joined_at
        '''), (household['id'],))
        household['members'] = [dict(r) for r in cur.fetchall()]
    return jsonify({'household': household})


@app.post('/api/household/create')
def create_household():
    init_db()
    user_id = current_user_id()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    body = request.get_json(silent=True) or {}
    name = (body.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Household name required'}), 400

    with db.connect() as conn:
        cur = conn.cursor()
        cur.execute(db.q('SELECT household_id FROM household_members WHERE user_id = ?'), (user_id,))
        if cur.fetchone():
            return jsonify({'error': 'You are already in a household. Leave it first.'}), 409

        invite_code = ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(8))

        if db.is_postgres:
            cur.execute(
                'INSERT INTO households(name, invite_code) VALUES (%s, %s) RETURNING id',
                (name, invite_code)
            )
            household_id = cur.fetchone()['id']
        else:
            cur.execute('INSERT INTO households(name, invite_code) VALUES (?, ?)', (name, invite_code))
            household_id = cur.lastrowid

        cur.execute(db.q('INSERT INTO household_members(household_id, user_id, role) VALUES (?, ?, ?)'),
                    (household_id, user_id, 'owner'))
        conn.commit()

    return jsonify({'id': household_id, 'name': name, 'invite_code': invite_code, 'role': 'owner'})


@app.post('/api/household/join')
def join_household():
    init_db()
    user_id = current_user_id()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    body = request.get_json(silent=True) or {}
    invite_code = (body.get('inviteCode') or '').strip().upper()
    if not invite_code:
        return jsonify({'error': 'Invite code required'}), 400

    with db.connect() as conn:
        cur = conn.cursor()
        cur.execute(db.q('SELECT household_id FROM household_members WHERE user_id = ?'), (user_id,))
        if cur.fetchone():
            return jsonify({'error': 'You are already in a household. Leave it first.'}), 409

        cur.execute(db.q('SELECT id, name FROM households WHERE invite_code = ?'), (invite_code,))
        household = cur.fetchone()
        if not household:
            return jsonify({'error': 'Invalid invite code.'}), 404

        cur.execute(db.q('INSERT INTO household_members(household_id, user_id, role) VALUES (?, ?, ?)'),
                    (household['id'], user_id, 'member'))
        conn.commit()

    return jsonify({'id': household['id'], 'name': household['name']})


@app.delete('/api/household/leave')
def leave_household():
    init_db()
    user_id = current_user_id()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    with db.connect() as conn:
        cur = conn.cursor()
        cur.execute(db.q('SELECT household_id, role FROM household_members WHERE user_id = ?'), (user_id,))
        member_row = cur.fetchone()
        if not member_row:
            return jsonify({'error': 'Not in a household'}), 404

        household_id = member_row['household_id']
        role = member_row['role']

        cur.execute(db.q('SELECT COUNT(*) AS count FROM household_members WHERE household_id = ?'), (household_id,))
        count_row = cur.fetchone()
        count = count_row['count']

        cur.execute(db.q('DELETE FROM household_members WHERE user_id = ?'), (user_id,))

        if count == 1:
            cur.execute(db.q('DELETE FROM households WHERE id = ?'), (household_id,))
        elif role == 'owner':
            cur.execute(db.q('SELECT user_id FROM household_members WHERE household_id = ? LIMIT 1'), (household_id,))
            next_member = cur.fetchone()
            if next_member:
                cur.execute(db.q('UPDATE household_members SET role = ? WHERE user_id = ? AND household_id = ?'),
                            ('owner', next_member['user_id'], household_id))
        conn.commit()

    return jsonify({'ok': True})


@app.get('/api/household/completions')
def get_household_completions():
    init_db()
    user_id = current_user_id()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    week = request.args.get('weekStart')
    if not week:
        return jsonify({'error': 'weekStart query required'}), 400

    with db.connect() as conn:
        cur = conn.cursor()
        cur.execute(db.q('SELECT household_id FROM household_members WHERE user_id = ?'), (user_id,))
        member_row = cur.fetchone()
        if not member_row:
            return jsonify({'members': [], 'completions': {}})

        household_id = member_row['household_id']
        cur.execute(db.q('''
            SELECT u.id, u.username
            FROM household_members hm
            JOIN users u ON u.id = hm.user_id
            WHERE hm.household_id = ?
            ORDER BY hm.joined_at
        '''), (household_id,))
        members = [dict(r) for r in cur.fetchall()]

        if not members:
            return jsonify({'members': [], 'completions': {}})

        member_ids = [m['id'] for m in members]
        if db.is_postgres:
            ph = ', '.join(['%s'] * len(member_ids))
            sql = f'SELECT user_id, task_id, completed FROM completions WHERE user_id IN ({ph}) AND week_start = %s'
        else:
            ph = ', '.join(['?'] * len(member_ids))
            sql = f'SELECT user_id, task_id, completed FROM completions WHERE user_id IN ({ph}) AND week_start = ?'

        cur.execute(sql, member_ids + [week])
        comp_rows = cur.fetchall()

        completions_by_task = {}
        for row in comp_rows:
            tid = row['task_id']
            uid = row['user_id']
            if tid not in completions_by_task:
                completions_by_task[tid] = {}
            completions_by_task[tid][uid] = bool(row['completed'])

    return jsonify({'members': members, 'completions': completions_by_task})


@app.post('/api/tasks')
def create_task():
    init_db()
    user_id = current_user_id()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    body = request.get_json(silent=True) or {}
    section = (body.get('section') or '').strip()
    label = (body.get('label') or '').strip()

    if not section or not label:
        return jsonify({'error': 'section and label required'}), 400
    if section not in VALID_SECTIONS:
        return jsonify({'error': 'Invalid section'}), 400

    frequency = get_frequency_for_section(section)

    with db.connect() as conn:
        cur = conn.cursor()
        cur.execute(db.q('SELECT COALESCE(MAX(sort_order), -1) + 1 AS next_order FROM tasks WHERE section = ?'), (section,))
        row = cur.fetchone()
        next_order = row['next_order']

        if db.is_postgres:
            cur.execute(
                'INSERT INTO tasks(section, frequency, label, sort_order) VALUES (%s, %s, %s, %s) RETURNING id',
                (section, frequency, label, next_order)
            )
            task_id = cur.fetchone()['id']
        else:
            cur.execute(db.q('INSERT INTO tasks(section, frequency, label, sort_order) VALUES (?, ?, ?, ?)'),
                        (section, frequency, label, next_order))
            task_id = cur.lastrowid
        conn.commit()

    return jsonify({'id': task_id, 'section': section, 'frequency': frequency, 'label': label, 'sort_order': next_order})


@app.put('/api/tasks/<int:task_id>')
def update_task(task_id):
    init_db()
    user_id = current_user_id()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    body = request.get_json(silent=True) or {}
    label = (body.get('label') or '').strip()
    section = (body.get('section') or '').strip()

    if not label or not section:
        return jsonify({'error': 'label and section required'}), 400
    if section not in VALID_SECTIONS:
        return jsonify({'error': 'Invalid section'}), 400

    frequency = get_frequency_for_section(section)

    with db.connect() as conn:
        cur = conn.cursor()
        cur.execute(db.q('SELECT section, sort_order FROM tasks WHERE id = ?'), (task_id,))
        existing = cur.fetchone()
        if not existing:
            return jsonify({'error': 'Task not found'}), 404

        new_sort_order = existing['sort_order']
        if section != existing['section']:
            cur.execute(db.q('SELECT COALESCE(MAX(sort_order), -1) + 1 AS next_order FROM tasks WHERE section = ?'), (section,))
            row = cur.fetchone()
            new_sort_order = row['next_order']

        cur.execute(db.q('UPDATE tasks SET label = ?, section = ?, frequency = ?, sort_order = ? WHERE id = ?'),
                    (label, section, frequency, new_sort_order, task_id))
        conn.commit()

    return jsonify({'ok': True})


@app.delete('/api/tasks/<int:task_id>')
def delete_task(task_id):
    init_db()
    user_id = current_user_id()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    with db.connect() as conn:
        cur = conn.cursor()
        cur.execute(db.q('DELETE FROM completions WHERE task_id = ?'), (task_id,))
        cur.execute(db.q('DELETE FROM tasks WHERE id = ?'), (task_id,))
        conn.commit()

    return jsonify({'ok': True})


@app.post('/api/tasks/reorder')
def reorder_tasks():
    init_db()
    user_id = current_user_id()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    body = request.get_json(silent=True) or {}
    items = body.get('items') or []
    if not isinstance(items, list):
        return jsonify({'error': 'items must be a list'}), 400

    with db.connect() as conn:
        cur = conn.cursor()
        for item in items:
            if not isinstance(item, dict):
                continue
            item_id = item.get('id')
            item_order = item.get('sort_order')
            if not isinstance(item_id, int) or not isinstance(item_order, int):
                continue
            cur.execute(db.q('UPDATE tasks SET sort_order = ? WHERE id = ?'), (item_order, item_id))
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
