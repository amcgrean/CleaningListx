import json
import os
import secrets
import sqlite3
from datetime import datetime
from http import cookies
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import hashlib

ROOT = Path(__file__).parent
PUBLIC_DIR = ROOT / 'public'
DB_PATH = ROOT / 'cleaning.db'

SESSIONS = {}

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


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 200000)
    return f"{salt}${digest.hex()}"


def verify_password(password, encoded):
    salt, _ = encoded.split('$', 1)
    return hash_password(password, salt) == encoded


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.executescript('''
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT UNIQUE NOT NULL,
      password_hash TEXT NOT NULL,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS tasks (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      section TEXT NOT NULL,
      frequency TEXT NOT NULL,
      label TEXT NOT NULL,
      sort_order INTEGER NOT NULL,
      UNIQUE(section, label)
    );
    CREATE TABLE IF NOT EXISTS completions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      task_id INTEGER NOT NULL,
      week_start TEXT NOT NULL,
      completed INTEGER NOT NULL DEFAULT 0,
      updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(user_id, task_id, week_start)
    );
    ''')
    if cur.execute('SELECT COUNT(*) FROM tasks').fetchone()[0] == 0:
        for section, labels in WEEKLY_SECTIONS.items():
            for idx, label in enumerate(labels):
                cur.execute('INSERT INTO tasks(section, frequency, label, sort_order) VALUES (?, ?, ?, ?)',
                            (section, 'weekly', label, idx))
        for idx, label in enumerate(MONTHLY):
            cur.execute('INSERT INTO tasks(section, frequency, label, sort_order) VALUES (?, ?, ?, ?)',
                        ('Monthly', 'monthly', label, idx))
        for idx, (month, label) in enumerate(ANNUAL):
            cur.execute('INSERT INTO tasks(section, frequency, label, sort_order) VALUES (?, ?, ?, ?)',
                        (f'Annual {month}', 'annual', label, idx))
    conn.commit()
    conn.close()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC_DIR), **kwargs)

    def _json_body(self):
        length = int(self.headers.get('Content-Length', '0'))
        raw = self.rfile.read(length) if length else b'{}'
        return json.loads(raw.decode() or '{}')

    def _send_json(self, payload, status=200, extra_headers=None):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _session(self):
        raw = self.headers.get('Cookie', '')
        jar = cookies.SimpleCookie(raw)
        sid = jar['sid'].value if 'sid' in jar else None
        return sid, SESSIONS.get(sid)

    def _require_user(self):
        _, user_id = self._session()
        return user_id

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith('/api/'):
            return self.api_get(parsed)
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith('/api/'):
            return self.api_post(parsed)
        self.send_error(404)

    def api_get(self, parsed):
        conn = get_conn()
        user_id = self._require_user()

        if parsed.path == '/api/auth/me':
            if not user_id:
                return self._send_json({'user': None})
            user = conn.execute('SELECT id, username FROM users WHERE id = ?', (user_id,)).fetchone()
            return self._send_json({'user': dict(user) if user else None})

        if not user_id:
            return self._send_json({'error': 'Unauthorized'}, 401)

        if parsed.path == '/api/tasks':
            rows = [dict(r) for r in conn.execute('SELECT id, section, frequency, label, sort_order FROM tasks ORDER BY id')]
            return self._send_json({'tasks': rows})

        if parsed.path == '/api/completions':
            qs = parse_qs(parsed.query)
            week = qs.get('weekStart', [None])[0]
            if not week:
                return self._send_json({'error': 'weekStart query required'}, 400)
            rows = conn.execute('SELECT task_id, completed FROM completions WHERE user_id = ? AND week_start = ?',
                                (user_id, week)).fetchall()
            return self._send_json({'completions': {r['task_id']: bool(r['completed']) for r in rows}})

        return self._send_json({'error': 'Not found'}, 404)

    def api_post(self, parsed):
        conn = get_conn()
        body = self._json_body()

        if parsed.path == '/api/auth/register':
            username = (body.get('username') or '').strip()
            password = body.get('password') or ''
            if not username or len(password) < 6:
                return self._send_json({'error': 'Provide username and password (6+ chars).'}, 400)
            try:
                cur = conn.execute('INSERT INTO users(username, password_hash) VALUES (?, ?)',
                                   (username, hash_password(password)))
                conn.commit()
            except sqlite3.IntegrityError:
                return self._send_json({'error': 'Username already exists.'}, 409)
            sid = secrets.token_urlsafe(24)
            SESSIONS[sid] = cur.lastrowid
            return self._send_json({'id': cur.lastrowid, 'username': username}, extra_headers={
                'Set-Cookie': f'sid={sid}; Path=/; HttpOnly; SameSite=Lax'
            })

        if parsed.path == '/api/auth/login':
            username = (body.get('username') or '').strip()
            password = body.get('password') or ''
            user = conn.execute('SELECT id, username, password_hash FROM users WHERE username = ?', (username,)).fetchone()
            if not user or not verify_password(password, user['password_hash']):
                return self._send_json({'error': 'Invalid credentials.'}, 401)
            sid = secrets.token_urlsafe(24)
            SESSIONS[sid] = user['id']
            return self._send_json({'id': user['id'], 'username': user['username']}, extra_headers={
                'Set-Cookie': f'sid={sid}; Path=/; HttpOnly; SameSite=Lax'
            })

        if parsed.path == '/api/auth/logout':
            sid, _ = self._session()
            if sid and sid in SESSIONS:
                del SESSIONS[sid]
            return self._send_json({'ok': True}, extra_headers={
                'Set-Cookie': 'sid=deleted; Path=/; Max-Age=0; HttpOnly; SameSite=Lax'
            })

        user_id = self._require_user()
        if not user_id:
            return self._send_json({'error': 'Unauthorized'}, 401)

        if parsed.path == '/api/completions':
            week = body.get('weekStart')
            task_id = body.get('taskId')
            completed = body.get('completed')
            if not week or not isinstance(task_id, int) or not isinstance(completed, bool):
                return self._send_json({'error': 'Invalid payload'}, 400)
            conn.execute('''
            INSERT INTO completions(user_id, task_id, week_start, completed, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, task_id, week_start)
            DO UPDATE SET completed=excluded.completed, updated_at=excluded.updated_at
            ''', (user_id, task_id, week, int(completed), datetime.utcnow().isoformat()))
            conn.commit()
            return self._send_json({'ok': True})

        return self._send_json({'error': 'Not found'}, 404)


def main():
    init_db()
    port = int(os.environ.get('PORT', '3000'))
    server = ThreadingHTTPServer(('0.0.0.0', port), Handler)
    print(f'Cleaning Listx running on http://localhost:{port}')
    server.serve_forever()


if __name__ == '__main__':
    main()
