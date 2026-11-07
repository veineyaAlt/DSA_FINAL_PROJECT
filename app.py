#!/usr/bin/env python3
"""Secret Santa — веб-приложение на Flask + SQLite.

Маршруты:
  /register /login /logout    — аккаунты и сессии
  /groups                     — мои группы, создание, вход по коду
  /groups/create                    POST — создать группу
  /groups/join                      POST — присоединиться по коду
  /groups/<id>                — группа: состав, вишлисты, панель инициатора
  /groups/<id>/wish            POST — добавить желание
  /groups/<id>/wish/<wid>/del  POST — удалить своё желание
  /groups/<id>/exclude          POST — добавить запрет (инициатор)
  /groups/<id>/exclude/<eid>/del POST — удалить запрет (инициатор)
  /groups/<id>/draw             POST — жеребьевка (инициатор)
  /groups/<id>/feedback         POST — отзыв о полученном подарке
  /groups/<id>/delete           POST — удалить группу (инициатор)
"""
import secrets
import re
import string
from datetime import date

from flask import (Flask, abort, flash, g, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_conn, init_db

app = Flask(__name__)
app.config["SECRET_KEY"] = "change-me-in-production"
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0  # статика всегда свежая, версионирование через ?v=<mtime>


@app.template_filter("vfile")
def versioned_static(filename):
    """URL статического файла с ?v=<mtime>: браузер всегда берёт свежую версию."""
    import os
    full = os.path.join(app.static_folder, filename)
    try:
        v = int(os.stat(full).st_mtime)
    except OSError:
        v = 0
    return f"{url_for('static', filename=filename)}?v={v}"


app.jinja_env.globals["vstatic"] = versioned_static

EV_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ------------------------------------------------------------------ helpers
def gen_code(n=8):
    alpha = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alpha) for _ in range(n))


def ensure_db():
    try:
        get_conn().execute("SELECT 1 FROM users LIMIT 1").fetchone()
        return True
    except Exception:
        return False


if not ensure_db():
    init_db()


@app.before_request
def open_conn():
    g.conn = get_conn()
    g.user = None
    uid = session.get("uid")
    if uid is not None:
        g.user = g.conn.execute(
            "SELECT user_id, email, display_name FROM users WHERE user_id=?",
            (uid,)).fetchone()


@app.teardown_appcontext
def close_conn(_exc):
    conn = g.pop("conn", None)
    if conn is not None:
        conn.close()


def need_login():
    if g.user is None:
        flash("Please log in first.", "warning")
        return True
    return False


def q(sql, args=(), one=False):
    rows = g.conn.execute(sql, args).fetchall()
    return (rows[0] if rows else None) if one else rows


def get_group(gid):
    grp = q("SELECT * FROM groups WHERE group_id=?", (gid,), one=True)
    if not grp:
        abort(404)
    return grp


def is_member(gid):
    return q("SELECT 1 FROM membership WHERE group_id=? AND user_id=?",
             (gid, g.user["user_id"]), one=True) is not None


def is_organizer(grp):
    return g.user is not None and grp["organizer_id"] == g.user["user_id"]


# -------------------------------------------------------------------- auth
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        name = request.form["name"].strip()
        pw = request.form["password"]
        if not email or not name or len(pw) < 6:
            flash("Fill in all fields; password must be at least 6 characters.", "danger")
        elif q("SELECT 1 FROM users WHERE email=?", (email,), one=True):
            flash("This email is already registered.", "danger")
        else:
            cur = g.conn.execute(
                "INSERT INTO users(email, password_hash, display_name) VALUES (?,?,?)",
                (email, generate_password_hash(pw), name))
            g.conn.commit()
            session["uid"] = cur.lastrowid
            flash("Welcome aboard!", "success")
            return redirect(url_for("groups"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        row = q("SELECT * FROM users WHERE email=?",
                (request.form["email"].strip().lower(),), one=True)
        if row and check_password_hash(row["password_hash"], request.form["password"]):
            session["uid"] = row["user_id"]
            flash(f"Hi, {row['display_name']}!", "success")
            return redirect(url_for("groups"))
        flash("Wrong email or password.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("uid", None)
    return redirect(url_for("login"))


# ------------------------------------------------------------------ группы
@app.route("/")
def landing():
    if g.user is not None:
        return redirect(url_for("groups"))
    return render_template("landing.html")


@app.route("/health")
def health():
    return "ok", 200


@app.route("/groups")
def groups():
    if need_login():
        return redirect(url_for("login"))
    mine = q("""SELECT g.group_id, g.group_name, g.event_date, g.status, g.join_code,
                       COUNT(m.user_id) AS member_count
                FROM groups g JOIN membership m ON m.group_id = g.group_id
                WHERE g.group_id IN (SELECT group_id FROM membership WHERE user_id=?)
                GROUP BY g.group_id ORDER BY g.event_date""",
             (g.user["user_id"],))
    # Q4: дашборд открытых групп (из VIEW), без тех, где я уже состою
    open_groups = q("""SELECT v.group_id, v.group_name, v.event_date, v.join_deadline,
                              v.budget_hint, v.member_count, v.wish_count
                       FROM view_open_groups v
                       WHERE v.group_id NOT IN
                             (SELECT group_id FROM membership WHERE user_id=?)
                       ORDER BY v.event_date""",
                    (g.user["user_id"],))
    return render_template("groups.html", groups=mine, open_groups=open_groups)


@app.route("/groups/create", methods=["POST"])
def group_create():
    name = request.form["name"].strip()
    ev, dl = request.form["event_date"], request.form["join_deadline"]
    budget = request.form.get("budget_hint", "").strip()
    if not (3 <= len(name) <= 80) or not EV_RE.match(ev) or not EV_RE.match(dl) or dl > ev:
        flash("Check the name and dates (deadline ≤ event date).", "danger")
        return redirect(url_for("groups"))
    if dl < date.today().isoformat():
        flash("The deadline cannot be in the past.", "danger")
        return redirect(url_for("groups"))
    code = gen_code()
    while q("SELECT 1 FROM groups WHERE join_code=?", (code,), one=True):
        code = gen_code()
    cur = g.conn.execute(
        "INSERT INTO groups(organizer_id, group_name, event_date, join_deadline, budget_hint, join_code)"
        " VALUES (?,?,?,?,?,?)",
        (g.user["user_id"], name, ev, dl, int(budget) if budget.isdigit() else None, code))
    g.conn.execute("INSERT INTO membership(group_id, user_id) VALUES (?,?)",
                   (cur.lastrowid, g.user["user_id"]))
    g.conn.commit()
    flash("Group created. Send the code to your friends.", "success")
    return redirect(url_for("group_page", gid=cur.lastrowid))


@app.route("/groups/join", methods=["POST"])
def group_join():
    code = request.form["code"].strip().upper()
    grp = q("SELECT * FROM groups WHERE join_code=?", (code,), one=True)
    if not grp:
        flash("No group found for this code.", "danger")
    elif grp["status"] != "open":
        flash("The draw is already done; joining is closed.", "warning")
    elif grp["join_deadline"] < date.today().isoformat():
        flash("The join deadline has passed.", "warning")
    elif is_member(grp["group_id"]):
        flash("You are already a member.", "info")
        return redirect(url_for("group_page", gid=grp["group_id"]))
    else:
        g.conn.execute("INSERT INTO membership(group_id, user_id) VALUES (?,?)",
                       (grp["group_id"], g.user["user_id"]))
        g.conn.commit()
        flash("You joined!", "success")
    return redirect(url_for("groups"))


@app.route("/groups/<int:gid>")
def group_page(gid):
    if need_login():
        return redirect(url_for("login"))
    grp = get_group(gid)
    org = is_organizer(grp)
    if not (org or is_member(gid)):
        abort(403)

    members = q("""SELECT u.user_id, u.display_name,
                          COUNT(w.wish_id) AS wish_count
                   FROM membership m JOIN users u ON u.user_id = m.user_id
                   LEFT JOIN wishes w ON w.group_id = m.group_id
                                      AND w.user_id = m.user_id
                   WHERE m.group_id = ?
                   GROUP BY u.user_id ORDER BY u.display_name""", (gid,))
    my_wishes = q("""SELECT * FROM wishes
                     WHERE group_id=? AND user_id=? ORDER BY priority, wish_id""",
                  (gid, g.user["user_id"]))
    exclusions = q("""SELECT e.exclusion_id, a.display_name AS from_name,
                             b.display_name AS target_name, e.reason
                      FROM exclusions e
                      JOIN users a ON a.user_id = e.user_id
                      JOIN users b ON b.user_id = e.target_user_id
                      WHERE e.group_id=?""", (gid,)) if org else []

    my_receiver = q("""SELECT u.*, a.secret_code
                       FROM assignments a JOIN users u ON u.user_id = a.receiver_id
                       WHERE a.group_id=? AND a.giver_id=?""",
                     (gid, g.user["user_id"]), one=True)
    recv_wishes = []
    if my_receiver:
        recv_wishes = q("""SELECT wish_title, wish_url, wish_note, priority
                           FROM wishes WHERE group_id=? AND user_id=?
                           ORDER BY priority, wish_id""",
                        (gid, my_receiver["user_id"]))
    my_feedback = q("""SELECT f.rating, f.comment, u.display_name AS got
                       FROM feedback f JOIN assignments a ON a.assignment_id=f.assignment_id
                       JOIN users u ON u.user_id=a.receiver_id
                       WHERE a.group_id=? AND a.giver_id=?""",
                     (gid, g.user["user_id"]), one=True)

    # Q6 (организатор): отчёт по отзывам из VIEW + построчные оценки подарков
    report = q("SELECT * FROM view_gift_reports WHERE group_id=?", (gid,), one=True) \
        if org else None
    gift_rows = q("""SELECT a.assignment_id,
                            ga.display_name AS giver, ra.display_name AS receiver,
                            f.rating, f.comment
                     FROM assignments a
                     JOIN users ga ON ga.user_id = a.giver_id
                     JOIN users ra ON ra.user_id = a.receiver_id
                     LEFT JOIN feedback f ON f.assignment_id = a.assignment_id
                     WHERE a.group_id=?
                     ORDER BY f.rating IS NULL, f.rating DESC""", (gid,)) if org else []

    return render_template("group.html", grp=grp, org=org, members=members,
                           my_wishes=my_wishes, exclusions=exclusions,
                           recv=my_receiver, recv_wishes=recv_wishes,
                           feedback=my_feedback, report=report, gift_rows=gift_rows)


@app.route("/groups/<int:gid>/wish", methods=["POST"])
def wish_add(gid):
    grp = get_group(gid)
    if not (is_member(gid) and grp["status"] == "open"):
        flash("Wishes can be added only before the draw.", "warning")
        return redirect(url_for("group_page", gid=gid))
    title = request.form["title"].strip()
    prio = int(request.form.get("priority", "2") or 2)
    if not 1 <= prio <= 3:
        prio = 2
    if title:
        g.conn.execute(
            "INSERT INTO wishes(group_id, user_id, wish_title, wish_url, wish_note, priority)"
            " VALUES (?,?,?,?,?,?)",
            (gid, g.user["user_id"], title,
             request.form.get("url", "").strip() or None,
             request.form.get("note", "").strip() or None, prio))
        g.conn.commit()
    return redirect(url_for("group_page", gid=gid))


@app.route("/groups/<int:gid>/wish/<int:wid>/del", methods=["POST"])
def wish_del(gid, wid):
    g.conn.execute("DELETE FROM wishes WHERE wish_id=? AND group_id=? AND user_id=?",
                   (wid, gid, g.user["user_id"]))
    g.conn.commit()
    return redirect(url_for("group_page", gid=gid))


@app.route("/groups/<int:gid>/exclude", methods=["POST"])
def exclude_add(gid):
    grp = get_group(gid)
    if not (is_organizer(grp) and grp["status"] == "open"):
        abort(403)
    uid, tid = int(request.form["user_id"]), int(request.form["target_id"])
    member_ids = {m["user_id"] for m in q("SELECT user_id FROM membership WHERE group_id=?", (gid,))}
    if uid not in member_ids or tid not in member_ids:
        flash("Both participants must be members of this group.", "danger")
        return redirect(url_for("group_page", gid=gid))
    if uid == tid:
        flash("One cannot be forbidden to gift oneself.", "danger")
    elif q("SELECT 1 FROM exclusions WHERE group_id=? AND user_id=? AND target_user_id=?",
           (gid, uid, tid), one=True):
        flash("This exclusion already exists.", "info")
    else:
        g.conn.execute(
            "INSERT INTO exclusions(group_id, user_id, target_user_id, reason) VALUES (?,?,?,?)",
            (gid, uid, tid, request.form["reason"].strip() or None))
        g.conn.commit()
    return redirect(url_for("group_page", gid=gid))


@app.route("/groups/<int:gid>/exclude/<int:eid>/del", methods=["POST"])
def exclude_del(gid, eid):
    grp = get_group(gid)
    if not (is_organizer(grp) and grp["status"] == "open"):
        abort(403)
    g.conn.execute("DELETE FROM exclusions WHERE exclusion_id=? AND group_id=?",
                   (eid, gid))
    g.conn.commit()
    return redirect(url_for("group_page", gid=gid))


# ------------------------------------------------- жеребьевка с исключениями
def draw_pairs(conn, gid):
    """Дерайнджмент с запретами: собственный HashTable (dsa.py) + бэктрекинг."""
    from dsa import HashTable, draw_backtracking
    members = [r["user_id"] for r in
               conn.execute("SELECT user_id FROM membership WHERE group_id=?", (gid,))]
    blocked = HashTable()
    for giver, target in conn.execute(
            "SELECT user_id, target_user_id FROM exclusions WHERE group_id=?", (gid,)):
        s = blocked.get(giver)
        if s is None:
            s = set()
            blocked.set(giver, s)
        s.add(target)
    return draw_backtracking(members, blocked)


@app.route("/groups/<int:gid>/draw", methods=["POST"])
def group_draw(gid):
    grp = get_group(gid)
    if not (is_organizer(grp) and grp["status"] == "open"):
        abort(403)
    members = q("SELECT user_id FROM membership WHERE group_id=?", (gid,))
    if len(members) < 3:
        flash("At least 3 members are required.", "warning")
        return redirect(url_for("group_page", gid=gid))
    pairs = draw_pairs(g.conn, gid)
    if pairs is None:
        flash("Draw impossible: exclusions form a deadlock.", "danger")
        return redirect(url_for("group_page", gid=gid))
    for giver, receiver in pairs:
        code = gen_code(10)
        while q("SELECT 1 FROM assignments WHERE secret_code=?", (code,), one=True):
            code = gen_code(10)
        g.conn.execute(
            "INSERT INTO assignments(group_id, giver_id, receiver_id, secret_code)"
            " VALUES (?,?,?,?)", (gid, giver, receiver, code))
    g.conn.execute("UPDATE groups SET status='drawn' WHERE group_id=?", (gid,))
    g.conn.commit()
    flash("Draw completed! Check «who I gift». 🎉", "success")
    return redirect(url_for("group_page", gid=gid))


@app.route("/groups/<int:gid>/feedback", methods=["POST"])
def feedback_add(gid):
    grp = get_group(gid)
    if not (is_member(gid) and grp["status"] == "drawn"):
        abort(403)
    try:
        rating = int(request.form["rating"])
    except ValueError:
        rating = 0
    a = q("SELECT assignment_id FROM assignments WHERE group_id=? AND giver_id=?",
          (gid, g.user["user_id"]), one=True)
    if not (1 <= rating <= 5):
        flash("The rating must be between 1 and 5.", "danger")
    elif q("SELECT 1 FROM feedback WHERE assignment_id=?", (a["assignment_id"],), one=True):
        flash("You already submitted a rating.", "info")
    else:
        g.conn.execute(
            "INSERT INTO feedback(assignment_id, rating, comment) VALUES (?,?,?)",
            (a["assignment_id"], rating, request.form["comment"].strip() or None))
        g.conn.commit()
        flash("Thanks for your rating! ⭐", "success")
    return redirect(url_for("group_page", gid=gid))


@app.route("/groups/<int:gid>/delete", methods=["POST"])
def group_delete(gid):
    grp = get_group(gid)
    if not (is_organizer(grp) and is_member(gid)):
        abort(403)
    g.conn.execute("DELETE FROM groups WHERE group_id=?", (gid,))  # каскад удалит всё
    g.conn.commit()
    flash("Group deleted.", "info")
    return redirect(url_for("groups"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
