from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_bearer_token
from app.db import get_conn
from app.models import AttendanceRequest, BulkAttendanceRequest

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


@router.post("/mark_attendance", summary="Mark attendance for a single student")
def mark_attendance(req: AttendanceRequest) -> dict:
    with get_conn(read_only=False) as con:
        _mark_one(con, req.lesson_id, req.student_id)
    return {"message": "Attendance marked", "lesson_id": req.lesson_id, "student_id": req.student_id}


@router.post("/mark_attendance_bulk", summary="Mark attendance for many students at once")
def mark_attendance_bulk(req: BulkAttendanceRequest) -> dict:
    results = {"marked": [], "errors": []}
    with get_conn(read_only=False) as con:
        for sid in req.student_ids:
            try:
                _mark_one(con, req.lesson_id, sid)
                results["marked"].append(sid)
            except HTTPException as e:
                results["errors"].append({"student_id": sid, "detail": e.detail})
    return {
        "lesson_id": req.lesson_id,
        "marked_count": len(results["marked"]),
        **results,
    }
