from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_bearer_token
from app.db import get_conn
from app.models import ApplyPushes, AttendanceRequest, BulkAttendanceRequest, LessonParticipation
from app.routers.registration import _insert_registration

router = APIRouter(prefix="", tags=["attendance"], dependencies=[Depends(require_bearer_token)])


def _mark_one(con, lesson_id: int, student_id: int) -> None:
    if not con.execute("SELECT 1 FROM lesson WHERE lesson_id = ?", [lesson_id]).fetchone():
        raise HTTPException(404, detail=f"Lesson {lesson_id} not found.")

    if not con.execute(
        "SELECT 1 FROM course_registration WHERE student_id = ? AND lesson_id = ?",
        [student_id, lesson_id],
    ).fetchone():
        raise HTTPException(
            status_code=409,
            detail=f"Student {student_id} is not registered for lesson {lesson_id}.",
        )

    already = con.execute(
        "SELECT 1 FROM attendance WHERE student_id = ? AND lesson_id = ?",
        [student_id, lesson_id],
    ).fetchone()
    if already:
        return  # idempotent

    con.execute(
        "INSERT INTO attendance (student_id, lesson_id, attendance_datetime) VALUES (?, ?, ?)",
        [student_id, lesson_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
    )


def _credit_next_class(con, student_id: int, course_id: int, after_datetime: str) -> Optional[Dict]:
    """Register `student_id` for the earliest future lesson in `course_id` they aren't
    already in. Returns the lesson we landed on, or None if no slot was available."""
    rows = con.execute(
        """
        SELECT lesson_id, start_datetime
        FROM lesson
        WHERE course_id = ?
          AND strptime(start_datetime, '%Y-%m-%d %H:%M:%S') >
              strptime(?, '%Y-%m-%d %H:%M:%S')
        ORDER BY start_datetime
        """,
        [course_id, after_datetime],
    ).fetchall()
    for lesson_id, start_dt in rows:
        already = con.execute(
            "SELECT 1 FROM course_registration WHERE student_id = ? AND lesson_id = ?",
            [student_id, lesson_id],
        ).fetchone()
        if not already:
            _insert_registration(con, student_id, lesson_id, course_id)
            return {"lesson_id": lesson_id, "start_datetime": start_dt}
    return None


@router.post("/preview_absentees", summary="List students registered for a lesson but not marked attended, with a proposed next class")
def preview_absentees(req: LessonParticipation) -> Dict:
    with get_conn(read_only=True) as con:
        lesson = con.execute(
            "SELECT course_id, start_datetime FROM lesson WHERE lesson_id = ?", [req.lesson_id]
        ).fetchone()
        if not lesson:
            raise HTTPException(404, detail=f"Lesson {req.lesson_id} not found.")
        course_id, start = lesson

        absentees = con.execute(
            """
            SELECT r.student_id, s.name
            FROM course_registration r
            JOIN student s ON r.student_id = s.student_id
            WHERE r.lesson_id = ?
              AND NOT EXISTS (
                  SELECT 1 FROM attendance a
                  WHERE a.student_id = r.student_id AND a.lesson_id = r.lesson_id
              )
            ORDER BY s.name
            """,
            [req.lesson_id],
        ).fetchall()

        out: List[Dict] = []
        for sid, name in absentees:
            proposed = con.execute(
                """
                SELECT lesson_id, start_datetime
                FROM lesson
                WHERE course_id = ?
                  AND strptime(start_datetime, '%Y-%m-%d %H:%M:%S') >
                      strptime(?, '%Y-%m-%d %H:%M:%S')
                  AND lesson_id NOT IN (
                      SELECT lesson_id FROM course_registration WHERE student_id = ?
                  )
                ORDER BY start_datetime
                LIMIT 1
                """,
                [course_id, start, sid],
            ).fetchone()
            out.append({
                "student_id": sid,
                "student_name": name,
                "course_id": course_id,
                "proposed_lesson_id": proposed[0] if proposed else None,
                "proposed_start_datetime": proposed[1] if proposed else None,
            })

    return {"lesson_id": req.lesson_id, "course_id": course_id, "absentees": out}


@router.post("/apply_pushes", summary="Register absentees to chosen target lessons (or leave unassigned)")
def apply_pushes(req: ApplyPushes) -> Dict:
    applied: List[Dict] = []
    unassigned: List[int] = []
    errors: List[Dict] = []
    with get_conn(read_only=False) as con:
        for item in req.items:
            if item.target_lesson_id is None:
                unassigned.append(item.student_id)
                continue
            lesson = con.execute(
                "SELECT course_id FROM lesson WHERE lesson_id = ?", [item.target_lesson_id]
            ).fetchone()
            if not lesson:
                errors.append({"student_id": item.student_id, "detail": f"Lesson {item.target_lesson_id} not found."})
                continue
            course_id = lesson[0]
            already = con.execute(
                "SELECT 1 FROM course_registration WHERE student_id = ? AND lesson_id = ?",
                [item.student_id, item.target_lesson_id],
            ).fetchone()
            if not already:
                _insert_registration(con, item.student_id, item.target_lesson_id, course_id)
            applied.append({"student_id": item.student_id, "lesson_id": item.target_lesson_id})
    return {
        "applied_count": len(applied),
        "applied": applied,
        "unassigned_count": len(unassigned),
        "unassigned": unassigned,
        "errors": errors,
    }


@router.post("/mark_attendance", summary="Mark attendance for a single student")
def mark_attendance(req: AttendanceRequest) -> Dict:
    with get_conn(read_only=False) as con:
        _mark_one(con, req.lesson_id, req.student_id)
    return {"message": "Attendance marked", "lesson_id": req.lesson_id, "student_id": req.student_id}


@router.post("/mark_attendance_bulk", summary="Mark attendance for many students; optionally push absentees forward")
def mark_attendance_bulk(req: BulkAttendanceRequest) -> Dict:
    marked: List[int] = []
    errors: List[Dict] = []
    pushed: List[Dict] = []
    pushed_failed: List[Dict] = []

    with get_conn(read_only=False) as con:
        # Mark each provided student as attended.
        for sid in req.student_ids:
            try:
                _mark_one(con, req.lesson_id, sid)
                marked.append(sid)
            except HTTPException as e:
                errors.append({"student_id": sid, "detail": e.detail})

        if req.push_absent:
            row = con.execute(
                "SELECT l.course_id, l.start_datetime FROM lesson l WHERE l.lesson_id = ?",
                [req.lesson_id],
            ).fetchone()
            if not row:
                raise HTTPException(404, detail=f"Lesson {req.lesson_id} not found.")
            course_id, lesson_start = row[0], row[1]

            absent_rows = con.execute(
                """
                SELECT r.student_id, s.name
                FROM course_registration r
                JOIN student s ON r.student_id = s.student_id
                WHERE r.lesson_id = ?
                """,
                [req.lesson_id],
            ).fetchall()

            attended_set = set(req.student_ids)
            for sid, name in absent_rows:
                if sid in attended_set:
                    continue
                landed = _credit_next_class(con, sid, course_id, lesson_start)
                if landed:
                    pushed.append({
                        "student_id": sid,
                        "student_name": name,
                        "to_lesson_id": landed["lesson_id"],
                        "to_start_datetime": landed["start_datetime"],
                    })
                else:
                    pushed_failed.append({
                        "student_id": sid,
                        "student_name": name,
                        "reason": "No future lessons in this course to push to.",
                    })

    return {
        "lesson_id": req.lesson_id,
        "marked_count": len(marked),
        "marked": marked,
        "errors": errors,
        "pushed_count": len(pushed),
        "pushed": pushed,
        "pushed_failed": pushed_failed,
    }
