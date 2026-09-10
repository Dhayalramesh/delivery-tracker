"""
SQLite persistence layer for the Engagement Delivery Tracker.

SQLite instead of Postgres/Neon is a deliberate choice for this project —
see README.md for the reasoning. In short: this project's purpose is
demonstrating CI/testing discipline, and a CI pipeline that depends on a
live external database is slower and flakier than one that doesn't need
to reach the network at all. SQLite is file-based and needs zero setup,
which keeps `pytest` (and GitHub Actions) fast and dependency-free.

This module is intentionally kept separate from core/rules.py: the
business logic never touches SQL directly, so it stays unit-testable
without a database in play at all.
"""

import sqlite3
from contextlib import contextmanager
from datetime import date

DB_PATH = "tracker.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS engagements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_name TEXT NOT NULL,
    engagement_name TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sprints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id INTEGER NOT NULL REFERENCES engagements(id),
    sprint_number INTEGER NOT NULL,
    goal TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sprint_id INTEGER NOT NULL REFERENCES sprints(id),
    title TEXT NOT NULL,
    owner TEXT NOT NULL,
    story_points INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'Backlog',
    completed_date TEXT
);

CREATE TABLE IF NOT EXISTS qa_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id),
    name TEXT NOT NULL,
    passed INTEGER NOT NULL DEFAULT 0,
    checked_by TEXT DEFAULT ''
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def reset_db():
    with get_conn() as conn:
        conn.executescript("""
            DROP TABLE IF EXISTS qa_checks;
            DROP TABLE IF EXISTS tasks;
            DROP TABLE IF EXISTS sprints;
            DROP TABLE IF EXISTS engagements;
        """)
    init_db()


# ---------------- engagements ----------------

def add_engagement(client_name, engagement_name, start_date, end_date):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO engagements (client_name, engagement_name, start_date, end_date) "
            "VALUES (?, ?, ?, ?)",
            (client_name, engagement_name, str(start_date), str(end_date)),
        )
        return cur.lastrowid


def get_engagements():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM engagements ORDER BY start_date")]


# ---------------- sprints ----------------

def add_sprint(engagement_id, sprint_number, goal, start_date, end_date):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO sprints (engagement_id, sprint_number, goal, start_date, end_date) "
            "VALUES (?, ?, ?, ?, ?)",
            (engagement_id, sprint_number, goal, str(start_date), str(end_date)),
        )
        return cur.lastrowid


def get_sprints(engagement_id=None):
    with get_conn() as conn:
        if engagement_id:
            rows = conn.execute(
                "SELECT * FROM sprints WHERE engagement_id = ? ORDER BY sprint_number",
                (engagement_id,),
            )
        else:
            rows = conn.execute("SELECT * FROM sprints ORDER BY sprint_number")
        return [dict(r) for r in rows]


# ---------------- tasks ----------------

def add_task(sprint_id, title, owner, story_points, qa_check_names):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO tasks (sprint_id, title, owner, story_points, status) "
            "VALUES (?, ?, ?, ?, 'Backlog')",
            (sprint_id, title, owner, story_points),
        )
        task_id = cur.lastrowid
        for name in qa_check_names:
            conn.execute(
                "INSERT INTO qa_checks (task_id, name, passed) VALUES (?, ?, 0)",
                (task_id, name),
            )
        return task_id


def get_tasks(sprint_id=None):
    with get_conn() as conn:
        if sprint_id:
            rows = conn.execute("SELECT * FROM tasks WHERE sprint_id = ?", (sprint_id,))
        else:
            rows = conn.execute("SELECT * FROM tasks")
        tasks = [dict(r) for r in rows]
        for t in tasks:
            qa_rows = conn.execute(
                "SELECT * FROM qa_checks WHERE task_id = ?", (t["id"],)
            )
            t["qa_checks"] = [dict(q) for q in qa_rows]
        return tasks


def update_task_status(task_id, new_status, completed_date=None):
    with get_conn() as conn:
        conn.execute(
            "UPDATE tasks SET status = ?, completed_date = ? WHERE id = ?",
            (new_status, str(completed_date) if completed_date else None, task_id),
        )


def set_qa_check(check_id, passed, checked_by):
    with get_conn() as conn:
        conn.execute(
            "UPDATE qa_checks SET passed = ?, checked_by = ? WHERE id = ?",
            (1 if passed else 0, checked_by, check_id),
        )