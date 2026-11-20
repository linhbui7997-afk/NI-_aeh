import os, sqlite3
from datetime import datetime, timezone
DB = os.getenv('DB_PATH', 'data/bot.sqlite3')
def conn():
    os.makedirs(os.path.dirname(DB) or '.', exist_ok=True)
    c=sqlite3.connect(DB); c.execute('PRAGMA foreign_keys=ON'); return c
def stamp(): return datetime.now(timezone.utc).isoformat(timespec='seconds')
def init_db():
    with conn() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS systems(name TEXT PRIMARY KEY, active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS accounts(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, username TEXT, system TEXT NOT NULL, account TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY, username TEXT, first_seen TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id INTEGER, action TEXT, detail TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS scanned_codes(digest TEXT PRIMARY KEY, code TEXT NOT NULL, source TEXT NOT NULL, post_url TEXT, message_id INTEGER, detected_at TEXT NOT NULL);''')
        c.executemany('INSERT OR IGNORE INTO systems(name,active) VALUES (?,1)', [('F8BET',),('NEW88',),('HI88',)])
def save_scanned_code(digest, code, source, post_url, message_id):
    with conn() as c:
        cur=c.execute('INSERT OR IGNORE INTO scanned_codes(digest,code,source,post_url,message_id,detected_at) VALUES (?,?,?,?,?,?)',(digest,code,source,post_url,message_id,stamp()))
        return cur.rowcount == 1
def add_account(uid, username, system, account):
    with conn() as c:
        c.execute('INSERT INTO users VALUES (?,?,?) ON CONFLICT(user_id) DO UPDATE SET username=excluded.username',(uid,username,stamp()))
        c.execute('INSERT INTO accounts(user_id,username,system,account,created_at) VALUES (?,?,?,?,?)',(uid,username,system,account,stamp()))
        c.execute('INSERT INTO audit_log(actor_id,action,detail,created_at) VALUES (?,?,?,?)',(uid,'account_added',f'{system}:{account}',stamp()))
def list_accounts(uid):
    with conn() as c: return c.execute('SELECT system,account,created_at FROM accounts WHERE user_id=? ORDER BY id DESC',(uid,)).fetchall()
def list_systems():
    with conn() as c: return c.execute('SELECT name,active FROM systems ORDER BY name').fetchall()
def add_system(name):
    with conn() as c: c.execute('INSERT OR IGNORE INTO systems(name,active) VALUES (?,1)',(name,))
def rename_system(old,new):
    with conn() as c:
        c.execute('UPDATE systems SET name=? WHERE name=?',(new,old)); c.execute('UPDATE accounts SET system=? WHERE system=?',(new,old))
def set_system_active(name):
    with conn() as c: c.execute('UPDATE systems SET active=1-active WHERE name=?',(name,))
def stats():
    with conn() as c: return c.execute('SELECT COUNT(*) FROM users').fetchone()[0], c.execute('SELECT COUNT(*) FROM accounts').fetchone()[0]
def list_users():
    with conn() as c: return c.execute('SELECT user_id,username FROM users ORDER BY first_seen DESC').fetchall()
