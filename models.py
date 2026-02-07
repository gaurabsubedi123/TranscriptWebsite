import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

DATABASE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'database.db')

def get_db():
    """Get database connection."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the database with users table."""
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

class User(UserMixin):
    def __init__(self, id, username, password_hash, is_admin=False):
        self.id = id
        self.username = username
        self.password_hash = password_hash
        self.is_admin = is_admin

    @staticmethod
    def get_by_id(user_id):
        """Get user by ID."""
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        conn.close()
        if user:
            return User(user['id'], user['username'], user['password_hash'], bool(user['is_admin']))
        return None

    @staticmethod
    def get_by_username(username):
        """Get user by username."""
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        if user:
            return User(user['id'], user['username'], user['password_hash'], bool(user['is_admin']))
        return None

    @staticmethod
    def create(username, password, is_admin=False):
        """Create a new user."""
        password_hash = generate_password_hash(password)
        conn = get_db()
        try:
            conn.execute(
                'INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)',
                (username, password_hash, int(is_admin))
            )
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            conn.close()
            return False

    def check_password(self, password):
        """Verify password."""
        return check_password_hash(self.password_hash, password)

    @staticmethod
    def get_all_users():
        """Get all users (for admin)."""
        conn = get_db()
        users = conn.execute('SELECT id, username, is_admin, created_at FROM users').fetchall()
        conn.close()
        return users
