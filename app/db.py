import os
import sqlite3

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,
    email      TEXT    NOT NULL UNIQUE,
    course     TEXT    NOT NULL,
    semester   INTEGER NOT NULL CHECK (semester BETWEEN 1 AND 12),
    created_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_students_course ON students(course);
"""


def init_db(path):
    """Create the database file and tables if they do not exist yet."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    try:
        conn.execute("PRAGMA journal_mode=WAL")  # better concurrent reads with Gunicorn workers
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE_PATH"], timeout=10)
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()
