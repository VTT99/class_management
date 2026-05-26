from datetime import date as date_cls
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import require_bearer_token
from app.db import get_conn
from datetime import datetime, timedelta

from app.models import ExtendCourse, NewCourse, NewLesson, NewLessonsBulk

router = APIRouter(prefix="", tags=["courses"], dependencies=[Depends(require_bearer_token)])


@router.get("/courses", summary="List all courses with lesson stats")
def list_courses() -> List[Dict]:
    with get_conn(read_only=True) as con:
        rows = con.execute(
            """
            SELECT c.course_id,
                   c.course_name,
                   c.active,
                   COUNT(l.lesson_id) AS lesson_count,
                   MIN(l.start_datetime) AS first_lesson,
                   MAX(l.start_datetime) AS last_lesson
            FROM course c
            LEFT JOIN lesson l ON l.course_id = c.course_id
            GROUP BY c.course_id, c.course_name, c.active
            ORDER BY c.course_name
            """
        ).fetchall()
    return [
        {
            "course_id": r[0],
            "course_name": r[1],
            "active": bool(r[2]),
            "lesson_count": int(r[3]),
            "first_lesson": r[4],
            "last_lesson": r[5],
        }
        for r in rows
    ]


@router.get("/course_future_students", summary="Students registered for any upcoming lesson in a course")
def course_future_students(course_id: int = Query(..., gt=0)) -> List[Dict]:
    with get_conn(read_only=True) as con:
        rows = con.execute(
            """
            SELECT s.student_id, s.name, COUNT(*) AS future_lessons,
                   MIN(l.start_datetime) AS next_lesson
            FROM course_registration r
            JOIN lesson l ON r.lesson_id = l.lesson_id
            JOIN student s ON r.student_id = s.student_id
            WHERE l.course_id = ?
              AND strptime(l.start_datetime, '%Y-%m-%d %H:%M:%S') >= current_timestamp
            GROUP BY s.student_id, s.name
            ORDER BY s.name
            """,
            [course_id],
        ).fetchall()
    return [
        {"student_id": r[0], "name": r[1], "future_lessons": int(r[2]), "next_lesson": r[3]}
        for r in rows
    ]


@router.post("/add_course", summary="Create a new course", status_code=201)
def add_course(req: NewCourse) -> Dict:
    with get_conn(read_only=False) as con:
        row = con.execute("SELECT MAX(course_id) FROM course").fetchone()
        new_id = (row[0] if row and row[0] is not None else 0) + 1
        con.execute(
            "INSERT INTO course (course_id, course_name, active) VALUES (?, ?, ?)",
            [new_id, req.course_name, req.active],
        )
    return {"message": "Course created.", "course_id": new_id, "course_name": req.course_name, "active": req.active}


@router.post("/extend_course", summary="Add N more weekly occurrences after the last existing one(s)")
def extend_course(req: ExtendCourse) -> Dict:
    """Detect every (weekday, start_time, end_time) pattern that this course
    has lessons for, and append `weeks` more occurrences after the latest
    occurrence of each pattern."""
    with get_conn(read_only=False) as con:
        if not con.execute("SELECT 1 FROM course WHERE course_id = ?", [req.course_id]).fetchone():
            raise HTTPException(404, detail=f"Course {req.course_id} not found.")

        # For each (weekday, start_time, end_time) slot, find the latest occurrence.
        patterns = con.execute(
            """
            SELECT
                strftime(strptime(start_datetime, '%Y-%m-%d %H:%M:%S'), '%A') AS weekday,
                strftime(strptime(start_datetime, '%Y-%m-%d %H:%M:%S'), '%H:%M:%S') AS start_t,
                strftime(strptime(end_datetime,   '%Y-%m-%d %H:%M:%S'), '%H:%M:%S') AS end_t,
                MAX(strptime(start_datetime, '%Y-%m-%d %H:%M:%S')) AS latest_start
            FROM lesson
            WHERE course_id = ?
            GROUP BY weekday, start_t, end_t
            """,
            [req.course_id],
        ).fetchall()

        if not patterns:
            raise HTTPException(
                status_code=400,
                detail="Course has no existing lessons to extrapolate from. Add one lesson first, then extend.",
            )

        row = con.execute("SELECT MAX(lesson_id) FROM lesson").fetchone()
        next_id = (row[0] if row and row[0] is not None else 0) + 1

        created = []
        for weekday, start_t, end_t, latest_start in patterns:
            # latest_start is a datetime; the patterns return it as a datetime from strptime.
            latest = latest_start if isinstance(latest_start, datetime) else datetime.strptime(str(latest_start), "%Y-%m-%d %H:%M:%S")
            for w in range(1, req.weeks + 1):
                new_start = latest + timedelta(weeks=w)
                # Recombine date with the original times (strftime'd to HH:MM:SS).
                new_start_str = f"{new_start.date()} {start_t}"
                new_end_str = f"{new_start.date()} {end_t}"
                con.execute(
                    "INSERT INTO lesson (lesson_id, start_datetime, end_datetime, course_id) VALUES (?, ?, ?, ?)",
                    [next_id, new_start_str, new_end_str, req.course_id],
                )
                created.append({
                    "lesson_id": next_id,
                    "start_datetime": new_start_str,
                    "end_datetime": new_end_str,
                    "weekday": weekday,
                })
                next_id += 1

    return {
        "message": f"Added {len(created)} lesson(s) across {len(patterns)} weekly slot(s).",
        "course_id": req.course_id,
        "patterns_extended": len(patterns),
        "lessons": created,
    }


@router.get("/lessons", summary="List lessons within a date range, with course names")
def list_lessons(
    start_date: date_cls = Query(..., description="Inclusive start date (YYYY-MM-DD)"),
    end_date: date_cls = Query(..., description="Inclusive end date (YYYY-MM-DD)"),
) -> List[Dict]:
    """Returns lessons whose start_datetime falls on or between start_date and end_date,
    ordered by start time. Includes course_name so the UI doesn't have to join twice."""
    with get_conn(read_only=True) as con:
        rows = con.execute(
            """
            SELECT l.lesson_id, l.course_id, c.course_name,
                   l.start_datetime, l.end_datetime
            FROM lesson l
            JOIN course c ON l.course_id = c.course_id
            WHERE strptime(l.start_datetime, '%Y-%m-%d %H:%M:%S') >= ?
              AND strptime(l.start_datetime, '%Y-%m-%d %H:%M:%S') < ?
            ORDER BY l.start_datetime
            """,
            [
                f"{start_date} 00:00:00",
                f"{end_date} 23:59:59",
            ],
        ).fetchall()
    return [
        {
            "lesson_id": r[0],
            "course_id": r[1],
            "course_name": r[2],
            "start_datetime": r[3],
            "end_datetime": r[4],
        }
        for r in rows
    ]


@router.post("/add_lesson", summary="Create a new lesson", status_code=201)
def add_lesson(lesson: NewLesson) -> Dict:
    with get_conn(read_only=False) as con:
        if not con.execute("SELECT 1 FROM course WHERE course_id = ?", [lesson.course_id]).fetchone():
            raise HTTPException(404, detail=f"Course {lesson.course_id} not found.")

        row = con.execute("SELECT MAX(lesson_id) FROM lesson").fetchone()
        new_id = (row[0] if row and row[0] is not None else 0) + 1

        con.execute(
            "INSERT INTO lesson (lesson_id, start_datetime, end_datetime, course_id) VALUES (?, ?, ?, ?)",
            [new_id, lesson.start_datetime, lesson.end_datetime, lesson.course_id],
        )
    return {
        "message": "Lesson created.",
        "lesson_id": new_id,
        "course_id": lesson.course_id,
        "start_datetime": lesson.start_datetime,
        "end_datetime": lesson.end_datetime,
    }


@router.post("/add_lessons_bulk", summary="Create many lessons in one request (any recurrence)", status_code=201)
def add_lessons_bulk(req: NewLessonsBulk) -> Dict:
    """Frontend computes the dates for whichever pattern the user picked
    (single, weekly on N days, daily, etc.) and sends them all here.

    Validates each timestamp format and that every course_id exists.
    Returns the list of created lessons with their assigned IDs.
    """
    # Validate timestamps and unique course set.
    course_ids = {spec.course_id for spec in req.lessons}
    for spec in req.lessons:
        for label, ts in (("start_datetime", spec.start_datetime), ("end_datetime", spec.end_datetime)):
            try:
                datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            except ValueError as e:
                raise HTTPException(422, detail=f"Bad {label!r} for course {spec.course_id}: {e}")

    with get_conn(read_only=False) as con:
        for cid in course_ids:
            if not con.execute("SELECT 1 FROM course WHERE course_id = ?", [cid]).fetchone():
                raise HTTPException(404, detail=f"Course {cid} not found.")

        row = con.execute("SELECT MAX(lesson_id) FROM lesson").fetchone()
        next_id = (row[0] if row and row[0] is not None else 0) + 1

        created = []
        for spec in req.lessons:
            con.execute(
                "INSERT INTO lesson (lesson_id, start_datetime, end_datetime, course_id) VALUES (?, ?, ?, ?)",
                [next_id, spec.start_datetime, spec.end_datetime, spec.course_id],
            )
            created.append({
                "lesson_id": next_id,
                "course_id": spec.course_id,
                "start_datetime": spec.start_datetime,
                "end_datetime": spec.end_datetime,
            })
            next_id += 1

    return {"message": f"Created {len(created)} lessons.", "lessons": created}


@router.get("/search_courses", summary="Search for courses + available start times")
def search_courses(course_name_partial: str = Query(..., min_length=1)) -> List[Dict]:
    with get_conn(read_only=True) as con:
        matching = con.execute(
            "SELECT course_id, course_name FROM course WHERE course_name ILIKE ?",
            [f"%{course_name_partial}%"],
        ).fetchall()
        if not matching:
            return []

        results = []
        for course_id, course_name in matching:
            times = con.execute(
                """
                SELECT DISTINCT
                    strftime(strptime(start_datetime, '%Y-%m-%d %H:%M:%S'), '%H:%M') AS start_time
                FROM lesson
                WHERE course_id = ?
                  AND strptime(start_datetime, '%Y-%m-%d %H:%M:%S')
                      BETWEEN current_timestamp AND (current_timestamp + interval '1 month')
                ORDER BY 1
                """,
                [course_id],
            ).fetchall()
            results.append({
                "course_id": course_id,
                "course_name": course_name,
                "available_start_times": [t[0] for t in times],
            })
    return results


@router.get("/lesson_participants", summary="Get students registered for a lesson")
def lesson_participants(lesson_id: int = Query(..., gt=0)) -> List[Dict]:
    with get_conn(read_only=True) as con:
        rows = con.execute(
            """
            SELECT r.student_id, s.name
            FROM course_registration r
            JOIN student s ON r.student_id = s.student_id
            WHERE r.lesson_id = ?
            ORDER BY s.name
            """,
            [lesson_id],
        ).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail=f"No participants found for lesson ID {lesson_id}.")
    return [{"student_id": r[0], "name": r[1]} for r in rows]
