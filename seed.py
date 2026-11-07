#!/usr/bin/env python3
"""Создание демонстрационной БД: schema + примерные данные."""
import os
import secrets
import string
from datetime import date, timedelta

from db import get_conn, DB_PATH, init_db
from werkzeug.security import generate_password_hash

_CODE = string.ascii_uppercase + string.digits


def gen_code(n=8):
    return "".join(secrets.choice(_CODE) for _ in range(n))


def add_user(conn, email, name, pw):
    import sqlite3
    cur = conn.execute(
        "INSERT INTO users(email, password_hash, display_name) VALUES (?,?,?)",
        (email, generate_password_hash(pw), name))
    return cur.lastrowid


def add_group(conn, org, name, ev, dl, budget):
    code = gen_code()
    while conn.execute("SELECT 1 FROM groups WHERE join_code=?", (code,)).fetchone():
        code = gen_code()
    cur = conn.execute(
        "INSERT INTO groups(organizer_id, group_name, event_date, join_deadline, budget_hint, join_code)"
        " VALUES (?,?,?,?,?,?)", (org, name, ev, dl, budget, code))
    g = cur.lastrowid
    conn.execute("INSERT INTO membership(group_id, user_id) VALUES (?,?)", (g, org))
    return g, code


def join(conn, g, u):
    conn.execute("INSERT INTO membership(group_id, user_id) VALUES (?,?)", (g, u))


def wish(conn, g, u, title, url=None, note=None, prio=2):
    conn.execute(
        "INSERT INTO wishes(group_id, user_id, wish_title, wish_url, wish_note, priority)"
        " VALUES (?,?,?,?,?,?)", (g, u, title, url, note, prio))


def exclude(conn, g, a, b, reason):
    conn.execute(
        "INSERT INTO exclusions(group_id, user_id, target_user_id, reason) VALUES (?,?,?,?)",
        (g, a, b, reason))


def assign(conn, g, giver, receiver):
    cur = conn.execute(
        "INSERT INTO assignments(group_id, giver_id, receiver_id, secret_code) VALUES (?,?,?,?)",
        (g, giver, receiver, gen_code(10)))
    conn.execute("UPDATE groups SET status='drawn' WHERE group_id=?", (g,))
    return cur.lastrowid


def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    init_db()
    conn = get_conn()

    u = {name: add_user(conn, f"{name}@ex.com", name, "demo1234")
         for name in ("alisher", "dilnoza", "nikita", "sabina", "temur", "lola", "aziz")}

    # Группа 1 — игрок дружной ифы, жеребьевка уже проведена
    g1, c1 = add_group(conn, u["alisher"],
                       "Office Christmas party 2026",
                       (date.today() + timedelta(days=14)).isoformat(),
                       (date.today() + timedelta(days=7)).isoformat(),
                       100000)
    for name in ("dilnoza", "nikita", "sabina", "temur"):
        join(conn, g1, u[name])

    wish(conn, g1, u["alisher"], "Book: Database Systems by C. J. Date", "https://books.uz/ddd", "any edition", 1)
    wish(conn, g1, u["alisher"], "Thermal mug", None, "dark color", 3)
    wish(conn, g1, u["dilnoza"], "Cat grooming brush", None, "I have a long-haired cat", 1)
    wish(conn, g1, u["dilnoza"], "Candles", None, None, 2)
    wish(conn, g1, u["nikita"], "Wool socks, 3 pairs", None, "size 42", 1)
    wish(conn, g1, u["sabina"], "1000-piece puzzle", None, None, 2)
    wish(conn, g1, u["temur"], "Pu-erh tea", None, None, 1)

    exclude(conn, g1, u["dilnoza"], u["nikita"], "муж и жена")
    exclude(conn, g1, u["nikita"], u["dilnoza"], "муж и жена")

    assign(conn, g1, u["alisher"], u["dilnoza"])
    assign(conn, g1, u["dilnoza"], u["nikita"])
    assign(conn, g1, u["nikita"], u["temur"])
    assign(conn, g1, u["sabina"], u["alisher"])
    assign(conn, g1, u["temur"], u["sabina"])

    fb1 = conn.execute(
        "SELECT assignment_id FROM assignments WHERE group_id=? AND giver_id=?", (g1, u["alisher"])
    ).fetchone()[0]
    conn.execute("INSERT INTO feedback(assignment_id, rating, comment) VALUES (?,?,?)",
                 (fb1, 5, "It fit perfectly!"))

    # Группа 2 — открытая, ждёт участников
    g2, c2 = add_group(conn, u["lola"],
                       "New Year at grandma's",
                       (date.today() + timedelta(days=30)).isoformat(),
                       (date.today() + timedelta(days=20)).isoformat(), None)
    join(conn, g2, u["aziz"])
    wish(conn, g2, u["lola"], "Movie tickets", None, None, 1)

    conn.commit()
    print("users :", list(u))
    print(f"group1: id={g1} code={c1} (drawn+feedback)")
    print(f"group2: id={g2} code={c2} (open)")
    print("login :", "любой email выше, пароль demo1234")


if __name__ == "__main__":
    main()
