from datetime import date as date_cls
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import require_bearer_token
from app.db import get_conn
from app.models import NewLesson

router = APIRouter(prefix="", tags=["courses"], dependencies=[Depends(require_bearer_token)])


@router.get("/courses", summary="List all courses")
def list_courses() -> List[Dict]:
    with get_conn(read_only=True) as con:
        rows = con.execute(
            "SELECT course_id, course_name, active FROM course ORDER BY course_name"
        ).fetchall()
    return [{"course_id": r[0], "course_name": r[1], "active": bool(r[2])} for r in rows]


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
