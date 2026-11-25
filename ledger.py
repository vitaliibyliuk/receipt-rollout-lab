import sqlite3
from contextlib import closing
from pathlib import Path


class Ledger:
    def __init__(self, location):
        self.location = Path(location)
        self.location.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.open()) as db, db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS submissions (
                    id INTEGER PRIMARY KEY,
                    group_code TEXT NOT NULL,
                    submission_key TEXT NOT NULL UNIQUE
                )
            """)

    def open(self):
        db = sqlite3.connect(self.location, timeout=3)
        db.row_factory = sqlite3.Row
        return db

    def register(self, group, key):
        with closing(self.open()) as db, db:
            inserted = db.execute(
                """INSERT INTO submissions(group_code, submission_key)
                   VALUES (?, ?) ON CONFLICT(submission_key) DO NOTHING
                   RETURNING id, group_code, submission_key""",
                (group, key),
            ).fetchone()
            if inserted is not None:
                return dict(inserted), True
            existing = db.execute(
                "SELECT * FROM submissions WHERE submission_key = ?", (key,)
            ).fetchone()
            return dict(existing), False

    def find(self, number):
        with closing(self.open()) as db:
            result = db.execute("SELECT * FROM submissions WHERE id = ?", (number,)).fetchone()
        return dict(result) if result is not None else None
