# db.py
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "data" / "app.db"


def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # -----------------------------
    # Saved courses (unique per user + course)
    # -----------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS saved_courses (
      user_id TEXT NOT NULL,
      course_id TEXT NOT NULL,
      created_at TEXT DEFAULT (datetime('now')),
      PRIMARY KEY(user_id, course_id)
    )
    """)

    # Helpful index for faster "get saved"
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_saved_courses_user_created
    ON saved_courses(user_id, created_at DESC)
    """)

    # -----------------------------
    # Feedback (like/dislike + optional comment)
    # Each click creates one row (history is kept).
    # -----------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS feedback (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id TEXT NOT NULL,
      course_id TEXT NOT NULL,
      rating INTEGER NOT NULL,                  -- +1 like, -1 dislike
      comment TEXT DEFAULT "",
      created_at TEXT DEFAULT (datetime('now'))
    )
    """)

    # Useful indexes for analysis/personalisation later
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_feedback_user_created
    ON feedback(user_id, created_at DESC)
    """)
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_feedback_course_created
    ON feedback(course_id, created_at DESC)
    """)
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_feedback_user_course
    ON feedback(user_id, course_id)
    """)

    # -----------------------------
    # Events (behaviour logging for personalisation)
    # Tracks: click / save / like (+ query used)
    # -----------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id TEXT NOT NULL,
      course_id TEXT NOT NULL,
      event_type TEXT NOT NULL,                 -- "click" | "save" | "like"
      query TEXT DEFAULT "",
      created_at TEXT DEFAULT (datetime('now'))
    )
    """)

    # Fast retrieval of recent events per user
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_events_user_created
    ON events(user_id, created_at DESC)
    """)

    # Optional: filter by type quickly (e.g., only "click")
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_events_user_type_created
    ON events(user_id, event_type, created_at DESC)
    """)

    # Optional: course-level analytics
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_events_course_created
    ON events(course_id, created_at DESC)
    """)

    conn.commit()
    conn.close()
