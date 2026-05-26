"""Seed the local DuckDB with 6 weeks of recurring lessons + registrations.

Idempotent: re-running skips lessons that already exist at the same
(course_id, start_datetime).

Use on your server when you want a populated calendar to play with,
without going through the Google Sheets round-trip. Run with:

    python -m scripts.seed_demo_lessons
"""

import logging
import sys
from datetime import datetime, timedelta

import duckdb

from app.config import get_settings
from app.routers.registration import _insert_registration

log = logging.getLogger(__name__)
logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s: %(message)s")

WEEKS = 6

# Patterns are by course index — i.e. apply to the first course, second, ...
PATTERNS_BY_COURSE_INDEX = [
    # Course 0: Mon 10:00, Wed 14:00 (each 1 hour)
    [(0, 10, 0, 60), (2, 14, 0, 60)],
    # Course 1: Tue 16:00, Thu 18:00, Fri 10:00 (each 1 hour)
    [(1, 16, 0, 60), (3, 18, 0, 60), (4, 10, 0, 60)],
]


def main() -> int:
    settings = get_settings()
    if not settings.duckdb_path.exists():
        log.error("DuckDB file not found at %s — populate it first.", settings.duckdb_path)
        return 1

    con = duckdb.connect(str(settings.duckdb_path), read_only=False)
    try:
        courses = con.execute("SELECT course_id, course_name FROM course ORDER BY course_id").fetchall()
        students = con.execute("SELECT student_id, name FROM student ORDER BY student_id").fetchall()
        if not courses:
            log.error("No courses in the DB. Add at least one course first.")
            return 1
        if not students:
            log.error("No students in the DB. Add at least one student first.")
            return 1

        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        monday_this_week = today - timedelta(days=today.weekday())

        row = con.execute("SELECT MAX(lesson_id) FROM lesson").fetchone()
        next_id = (row[0] if row and row[0] is not None else 0) + 1

        new_lessons = []
        for ci, (course_id, course_name) in enumerate(courses):
            pattern = PATTERNS_BY_COURSE_INDEX[ci % len(PATTERNS_BY_COURSE_INDEX)]
            for w in range(WEEKS):
                for (wd, hour, minute, dur_min) in pattern:
                    start = monday_this_week + timedelta(weeks=w, days=wd, hours=hour, minutes=minute)
                    end = start + timedelta(minutes=dur_min)
                    start_s = start.strftime("%Y-%m-%d %H:%M:%S")
                    end_s = end.strftime("%Y-%m-%d %H:%M:%S")
                    exists = con.execute(
                        "SELECT 1 FROM lesson WHERE course_id = ? AND start_datetime = ?",
                        [course_id, start_s],
                    ).fetchone()
                    if exists:
                        continue
                    con.execute(
                        "INSERT INTO lesson (lesson_id, start_datetime, end_datetime, course_id) "
                        "VALUES (?, ?, ?, ?)",
                        [next_id, start_s, end_s, course_id],
                    )
                    new_lessons.append((next_id, course_id, course_name, start))
                    next_id += 1

        log.info("Created %d new lessons (skipped existing matches).", len(new_lessons))

        # Register every student for every newly-created lesson.
        registrations_added = 0
        for lesson_id, course_id, course_name, _start in new_lessons:
            for student_id, _name in students:
                already = con.execute(
                    "SELECT 1 FROM course_registration WHERE student_id = ? AND lesson_id = ?",
                    [student_id, lesson_id],
                ).fetchone()
                if already:
                    continue
                _insert_registration(con, student_id, lesson_id, course_id)
                registrations_added += 1

        log.info("Added %d registrations.", registrations_added)
    finally:
        con.close()

    log.info("Done. Restart the backend so it sees the new rows (systemctl --user restart class-management).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
