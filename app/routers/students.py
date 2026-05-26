import logging
from datetime import date
from io import StringIO
from typing import Dict, List

import duckdb
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.auth import require_bearer_token
from app.db import get_conn
from app.models import NewStudent, StudentQuery
from app.services.lesson_status import label_lesson_status

log = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["students"], dependencies=[Depends(require_bearer_token)])


def _query_student_data(student_id: int) -> Dict:
    with get_conn(read_only=True) as con:
        student_df = con.execute(
            "SELECT * FROM student WHERE student_id = ?", [student_id]
        ).fetchdf()
        if student_df.empty:
            raise HTTPException(status_code=404, detail=f"Student with ID {student_id} not found")

        student_name = student_df.iloc[0]["name"]

        lessons_df = con.execute(
            """
            SELECT c.course_id, c.course_name, c.active,
                   l.lesson_id, l.start_datetime, l.end_datetime,
                   CASE WHEN a.attendance_datetime IS NOT NULL
                        THEN 'attended' ELSE 'unattended' END AS participation_status
            FROM course_registration r
            JOIN lesson l ON r.lesson_id = l.lesson_id
            JOIN course c ON l.course_id = c.course_id
            LEFT JOIN attendance a
                   ON r.student_id = a.student_id AND r.lesson_id = a.lesson_id
            WHERE r.student_id = ?
            ORDER BY c.course_id, l.start_datetime DESC
            """,
            [student_id],
        ).fetchdf()

        # paid count per course (SUM of purchase.count rows for this student).
        # If the `purchase` table doesn't exist on an older DB, treat paid = 0.
        try:
            paid_df = con.execute(
                """
                SELECT course_id, COALESCE(SUM(count), 0) AS paid, MAX(payment_method) AS payment_method
                FROM purchase
                WHERE student_id = ?
                GROUP BY course_id
                """,
                [student_id],
            ).fetchdf()
        except Exception:  # purchase table missing
            paid_df = pd.DataFrame(columns=["course_id", "paid", "payment_method"])

    paid_by_course = {int(r["course_id"]): int(r["paid"]) for _, r in paid_df.iterrows()}
    payment_by_course = {int(r["course_id"]): r["payment_method"] for _, r in paid_df.iterrows()}

    now = pd.Timestamp.now()
    if not lessons_df.empty:
        lessons_df["lesson_status"] = lessons_df.apply(
            lambda r: label_lesson_status(r["participation_status"], r["start_datetime"], now),
            axis=1,
        )

    course_summary: Dict = {}
    lessons_status: Dict = {}
    if not lessons_df.empty:
        for course_id, group in lessons_df.groupby("course_id"):
            cid = int(course_id)
            completed = int((group["lesson_status"] == "completed").sum())
            uncomplete = int((group["lesson_status"] == "uncomplete").sum())
            not_yet = int((group["lesson_status"] == "not-yet-complete").sum())
            paid = paid_by_course.get(cid, 0)
            # Redefined semantics from the user:
            #   outstanding = paid - completed (total classes still owed)
            #   unassigned  = outstanding without a scheduled future lesson
            outstanding = max(0, paid - completed)
            unassigned = max(0, outstanding - not_yet)
            course_summary[cid] = {
                "course_name": group.iloc[0]["course_name"],
                "student_id": student_id,
                "student_name": student_name,
                "paid": paid,
                "completed": completed,
                "uncomplete": uncomplete,
                "not_yet_complete": not_yet,
                "outstanding": outstanding,
                "unassigned": unassigned,
                "total": int(len(group)),
                "payment_method": payment_by_course.get(cid),
            }
            lessons_status[cid] = group.to_dict(orient="records")

    return {
        "student": student_df.to_dict(orient="records")[0],
        "course_summary": course_summary,
        "lessons": lessons_status,
    }


@router.post("/student_data", summary="Get detailed student information")
def get_student_data(query: StudentQuery) -> Dict:
    return _query_student_data(query.student_id)


@router.get("/search_students", summary="Search students by ID or partial name")
def search_students(q: str = Query(..., min_length=1, max_length=100)) -> List[Dict]:
    """Returns up to 20 matches. Numeric query matches student_id exactly
    and is also tried as a name fragment; non-numeric query is a case-
    insensitive name fragment."""
    pattern = f"%{q}%"
    with get_conn(read_only=True) as con:
        if q.isdigit():
            rows = con.execute(
                """
                SELECT student_id, name
                FROM student
                WHERE student_id = ? OR name ILIKE ?
                ORDER BY
                    CASE WHEN student_id = ? THEN 0 ELSE 1 END,
                    name
                LIMIT 20
                """,
                [int(q), pattern, int(q)],
            ).fetchall()
        else:
            rows = con.execute(
                """
                SELECT student_id, name
                FROM student
                WHERE name ILIKE ?
                ORDER BY name
                LIMIT 20
                """,
                [pattern],
            ).fetchall()
    return [{"student_id": r[0], "name": r[1]} for r in rows]


@router.post("/add_student", summary="Add a new student", status_code=201)
def add_student(student: NewStudent) -> Dict:
    with get_conn(read_only=False) as con:
        try:
            row = con.execute("SELECT MAX(student_id) FROM student").fetchone()
            new_id = (row[0] if row and row[0] is not None else 0) + 1
        except duckdb.CatalogException:
            log.warning("student table missing; assuming first insert")
            new_id = 1

        record = {
            "student_id": new_id,
            "name": student.name,
            "parent_contact": student.parent_contact,
            "gender": student.gender,
            "date_of_register": date.today(),
            "referee": student.referee,
            "payment_method": student.payment_method,
        }
        con.execute(
            """
            INSERT INTO student
                (student_id, name, parent_contact, gender,
                 date_of_register, referee, payment_method)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            list(record.values()),
        )

    return {"message": "Student added successfully", "student_id": new_id, "data": record}


@router.get("/students/{student_id}/lessons.csv", summary="Export a student's lessons as CSV")
def export_student_lessons_csv(student_id: int) -> StreamingResponse:
    data = _query_student_data(student_id)
    rows: List[Dict] = []
    for course_id, lessons in data["lessons"].items():
        course = data["course_summary"][course_id]
        for lesson in lessons:
            rows.append({
                "student_id": student_id,
                "student_name": data["student"]["name"],
                "course_id": course_id,
                "course_name": course["course_name"],
                "lesson_id": lesson["lesson_id"],
                "start_datetime": lesson["start_datetime"],
                "end_datetime": lesson["end_datetime"],
                "participation_status": lesson["participation_status"],
                "lesson_status": lesson["lesson_status"],
            })
    df = pd.DataFrame(rows)
    buf = StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="student_{student_id}_lessons.csv"'},
    )
