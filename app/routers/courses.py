from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import require_bearer_token
from app.db import get_conn

router = APIRouter(prefix="", tags=["courses"], dependencies=[Depends(require_bearer_token)])


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
