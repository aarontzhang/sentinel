import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash

def init_db():
    conn = sqlite3.connect('watchlist.db')
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            last_login TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            stock_ticker TEXT NOT NULL,
            company_name TEXT NOT NULL,
            date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(user_id, stock_ticker)
        )
    ''')

    conn.commit()
    conn.close()
    print("Database initialized successfully!")

def create_default_user():
    conn = sqlite3.connect('watchlist.db')
    cursor = conn.cursor()

    try:
        password_hash = generate_password_hash('password123')
        cursor.execute(
            'INSERT INTO users (username, password_hash, last_login) VALUES (?, ?, ?)',
            ('demo', password_hash, datetime.now())
        )
        conn.commit()
        print("Default user created! Username: demo, Password: password123")
    except sqlite3.IntegrityError:
        print("Default user already exists")

    conn.close()

if __name__ == '__main__':
    init_db()
    create_default_user()
