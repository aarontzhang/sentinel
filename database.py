import os
from datetime import datetime
from werkzeug.security import generate_password_hash

# Detect environment - use PostgreSQL if DATABASE_URL is set, otherwise SQLite
DATABASE_URL = os.getenv('DATABASE_URL')

if DATABASE_URL:
    # Production: PostgreSQL
    import psycopg2
    from psycopg2.extras import RealDictCursor

    def get_connection():
        """Get PostgreSQL connection"""
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

    def init_db():
        """Initialize PostgreSQL database schema"""
        conn = get_connection()
        cursor = conn.cursor()

        # PostgreSQL uses SERIAL instead of AUTOINCREMENT
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                last_login TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS watchlist (
                id SERIAL PRIMARY KEY,
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
        print("PostgreSQL database initialized successfully!")

    def create_default_user():
        """Create default demo user in PostgreSQL"""
        conn = get_connection()
        cursor = conn.cursor()

        try:
            password_hash = generate_password_hash('password123')
            # PostgreSQL uses %s placeholders
            cursor.execute(
                'INSERT INTO users (username, password_hash, last_login) VALUES (%s, %s, %s)',
                ('demo', password_hash, datetime.now())
            )
            conn.commit()
            print("Default user created! Username: demo, Password: password123")
        except psycopg2.IntegrityError:
            print("Default user already exists")
        except Exception as e:
            print(f"Error creating default user: {e}")

        conn.close()

else:
    # Local development: SQLite
    import sqlite3

    def get_connection():
        """Get SQLite connection"""
        conn = sqlite3.connect('watchlist.db')
        conn.row_factory = sqlite3.Row
        return conn

    def init_db():
        """Initialize SQLite database schema"""
        conn = get_connection()
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
        print("SQLite database initialized successfully!")

    def create_default_user():
        """Create default demo user in SQLite"""
        conn = get_connection()
        cursor = conn.cursor()

        try:
            password_hash = generate_password_hash('password123')
            # SQLite uses ? placeholders
            cursor.execute(
                'INSERT INTO users (username, password_hash, last_login) VALUES (?, ?, ?)',
                ('demo', password_hash, datetime.now())
            )
            conn.commit()
            print("Default user created! Username: demo, Password: password123")
        except sqlite3.IntegrityError:
            print("Default user already exists")
        except Exception as e:
            print(f"Error creating default user: {e}")

        conn.close()

if __name__ == '__main__':
    init_db()
    create_default_user()
