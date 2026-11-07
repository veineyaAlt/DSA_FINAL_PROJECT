"""Подключение к БД и инициализация схемы."""
import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("SANTADB", os.path.join(BASE_DIR, "santa.db"))


def init_db(path=None):
    conn = sqlite3.connect(path or DB_PATH)
    conn.executescript(
        open(os.path.join(BASE_DIR, "schema.sql"), encoding="utf-8").read())
    conn.commit()
    conn.close()


def get_conn(path=None):
    conn = sqlite3.connect(path or DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
