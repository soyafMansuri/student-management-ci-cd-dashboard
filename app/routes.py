import re
import sqlite3
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, render_template, request

from .db import get_db

bp = Blueprint("students", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
COLUMNS = "id, name, email, course, semester, created_at"


def validate_student(data):
    """Return (clean_data, errors). errors is a dict of field -> message."""
    if not isinstance(data, dict):
        return None, {"body": "Request body must be a JSON object."}
    errors = {}
    name = str(data.get("name") or "").strip()
    email = str(data.get("email") or "").strip().lower()
    course = str(data.get("course") or "").strip()

    if not 2 <= len(name) <= 100:
        errors["name"] = "Name must be 2 to 100 characters."
    if len(email) > 120 or not EMAIL_RE.match(email):
        errors["email"] = "Enter a valid email address."
    if not 2 <= len(course) <= 100:
        errors["course"] = "Course must be 2 to 100 characters."

    semester = data.get("semester")
    try:
        if isinstance(semester, bool):
            raise ValueError
        semester = int(semester)
        if not 1 <= semester <= 12:
            raise ValueError
    except (TypeError, ValueError):
        errors["semester"] = "Semester must be a whole number from 1 to 12."

    if errors:
        return None, errors
    return {"name": name, "email": email, "course": course, "semester": semester}, {}


def row_to_dict(row):
    return {k: row[k] for k in row.keys()}


def json_body():
    return request.get_json(silent=True)


@bp.get("/")
def index():
    return render_template("index.html")


@bp.get("/api/health")
def health():
    try:
        get_db().execute("SELECT 1").fetchone()
        return jsonify(status="ok", database="ok", version=current_app.config["APP_VERSION"])
    except sqlite3.Error:
        return jsonify(status="error", database="unavailable",
                       version=current_app.config["APP_VERSION"]), 503


@bp.get("/api/students")
def list_students():
    q = (request.args.get("q") or "").strip()
    db = get_db()
    if q:
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        rows = db.execute(
            f"SELECT {COLUMNS} FROM students "
            "WHERE name LIKE ? ESCAPE '\\' OR email LIKE ? ESCAPE '\\' OR course LIKE ? ESCAPE '\\' "
            "ORDER BY id DESC",
            (like, like, like),
        ).fetchall()
    else:
        rows = db.execute(f"SELECT {COLUMNS} FROM students ORDER BY id DESC").fetchall()
    return jsonify([row_to_dict(r) for r in rows])


@bp.post("/api/students")
def create_student():
    clean, errors = validate_student(json_body())
    if errors:
        return jsonify(error="Validation failed.", errors=errors), 400
    db = get_db()
    created = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        cur = db.execute(
            "INSERT INTO students (name, email, course, semester, created_at) VALUES (?, ?, ?, ?, ?)",
            (clean["name"], clean["email"], clean["course"], clean["semester"], created),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify(error="Validation failed.",
                       errors={"email": "This email is already registered."}), 409
    row = db.execute(f"SELECT {COLUMNS} FROM students WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.get("/api/students/<int:student_id>")
def get_student(student_id):
    row = get_db().execute(f"SELECT {COLUMNS} FROM students WHERE id = ?", (student_id,)).fetchone()
    if row is None:
        return jsonify(error="Student not found."), 404
    return jsonify(row_to_dict(row))


@bp.put("/api/students/<int:student_id>")
def update_student(student_id):
    clean, errors = validate_student(json_body())
    if errors:
        return jsonify(error="Validation failed.", errors=errors), 400
    db = get_db()
    try:
        cur = db.execute(
            "UPDATE students SET name = ?, email = ?, course = ?, semester = ? WHERE id = ?",
            (clean["name"], clean["email"], clean["course"], clean["semester"], student_id),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify(error="Validation failed.",
                       errors={"email": "This email is already registered."}), 409
    if cur.rowcount == 0:
        return jsonify(error="Student not found."), 404
    row = db.execute(f"SELECT {COLUMNS} FROM students WHERE id = ?", (student_id,)).fetchone()
    return jsonify(row_to_dict(row))


@bp.delete("/api/students/<int:student_id>")
def delete_student(student_id):
    db = get_db()
    cur = db.execute("DELETE FROM students WHERE id = ?", (student_id,))
    db.commit()
    if cur.rowcount == 0:
        return jsonify(error="Student not found."), 404
    return jsonify(message="Student deleted.")


@bp.get("/api/stats")
def stats():
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM students").fetchone()[0]
    avg = db.execute("SELECT AVG(semester) FROM students").fetchone()[0]
    by_course = db.execute(
        "SELECT course, COUNT(*) AS count FROM students GROUP BY course ORDER BY count DESC, course LIMIT 5"
    ).fetchall()
    courses = db.execute("SELECT COUNT(DISTINCT course) FROM students").fetchone()[0]
    return jsonify(
        total=total,
        course_count=courses,
        average_semester=round(avg, 1) if avg is not None else 0,
        by_course=[row_to_dict(r) for r in by_course],
    )
