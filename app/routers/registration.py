from datetime import date, datetime
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_bearer_token
from app.db import get_conn
from app.models import NewRegistration, SingleRegistration

router = APIRouter(prefix="", tags=["registration"], dependencies=[Depends(require_bearer_token)])


def _course_registration_columns(con) -> List[str]:
    return [r[1] for r in con.execute("PRAGMA table_info('course_registration')").fetchall()]


def _insert_registration(con, student_id: int, lesson_id: int, course_id: int) -> None:
    """Insert a registration, adapting to whichever columns the table actually has.

    The seed scripts disagree on schema (some have `registration_id`, some include
    `course_id`), so we inspect the table and only populate columns that exist.
    """
    cols = _course_registration_columns(con)
    payload: Dict[str, object] = {
        "student_id": student_id,
        "lesson_id": lesson_id,
        "datetime_of_registration": datetime.now(),
        "status": "active",
    }
    if "course_id" in cols:
        payload["course_id"] = course_id
    if "registration_id" in cols:
        # Best-effort unique id; falls back to a synthetic string.
        next_id = con.execute("SELECT COUNT(*) FROM course_registration").fetchone()[0] + 1
        payload["registration_id"] = f"R_{next_id}"

    keep = [c for c in cols if c in payload]
    placeholders = ", ".join(["?"] * len(keep))
    sql = f"INSERT INTO course_registration ({', '.join(keep)}) VALUES ({placeholders})"
    con.execute(sql, [payload[c] for c in keep])


@router.post("/register_lessons", summary="Register a student for the next N lessons")
def register_lessons(reg: NewRegistration) -> Dict:
    with get_conn(read_only=False) as con:
        if not con.execute("SELECT 1 FROM student WHERE student_id = ?", [reg.student_id]).fetchone():
            raise HTTPException(404, detail=f"Student {reg.student_id} not found.")
        if not con.execute("SELECT 1 FROM course WHERE course_id = ?", [reg.course_id]).fetchone():
            raise HTTPException(404, detail=f"Course {reg.course_id} not found.")

        start_date = reg.first_lesson_date or date.today()

        lessons = con.execute(
            """
            SELECT lesson_id, start_datetime
            FROM lesson
            WHERE course_id = ?
              AND upper(strftime(strptime(start_datetime, '%Y-%m-%d %H:%M:%S'), '%A')) = upper(?)
              AND strftime(strptime(start_datetime, '%Y-%m-%d %H:%M:%S'), '%H:%M') = ?
              AND strptime(start_datetime, '%Y-%m-%d %H:%M:%S') >= ?
              AND lesson_id NOT IN (
                  SELECT lesson_id FROM course_registration
                  WHERE student_id = ? AND status = 'active'
              )
            ORDER BY start_datetime
            LIMIT ?
            """,
            [
                reg.course_id,
                reg.day_of_week,
                reg.start_time.strftime("%H:%M"),
                start_date,
                reg.student_id,
                reg.number_of_lessons,
            ],
        ).fetchall()

        if len(lessons) < reg.number_of_lessons:
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "INSUFFICIENT_LESSONS_FOUND",
                    "message": (
                        f"Only found {len(lessons)} of {reg.number_of_lessons} requested lessons "
                        f"matching the criteria. Try a different day, time, or start date."
                    ),
                    "found_lessons": [lid for lid, _ in lessons],
                },
            )

        registered = []
        for lesson_id, start_dt in lessons:
            _insert_registration(con, reg.student_id, lesson_id, reg.course_id)
            registered.append({"lesson_id": lesson_id, "start_datetime": start_dt})

    return {
        "message": "Registration successful.",
        "student_id": reg.student_id,
        "course_id": reg.course_id,
        "registered_lessons_count": len(registered),
        "lessons": registered,
    }


@router.post("/add_lesson_registration", summary="Register a single student to a single specific lesson")
def add_lesson_registration(reg: SingleRegistration) -> Dict:
    with get_conn(read_only=False) as con:
        if not con.execute("SELECT 1 FROM student WHERE student_id = ?", [reg.student_id]).fetchone():
            raise HTTPException(404, detail=f"Student {reg.student_id} not found.")

        lesson_row = con.execute(
            "SELECT course_id FROM lesson WHERE lesson_id = ?", [reg.lesson_id]
        ).fetchone()
        if not lesson_row:
            raise HTTPException(404, detail=f"Lesson {reg.lesson_id} not found.")
        course_id = lesson_row[0]

        # Idempotent: re-registering is a no-op.
        already = con.execute(
            "SELECT 1 FROM course_registration WHERE student_id = ? AND lesson_id = ?",
            [reg.student_id, reg.lesson_id],
        ).fetchone()
        if already:
            return {
                "message": "Already registered (no-op).",
                "student_id": reg.student_id,
                "lesson_id": reg.lesson_id,
            }

        _insert_registration(con, reg.student_id, reg.lesson_id, course_id)

    return {
        "message": "Student registered for lesson.",
        "student_id": reg.student_id,
        "lesson_id": reg.lesson_id,
    }
