"""Push a clean demo dataset directly into the linked Google Sheet.

Writes student / course / lesson / course_registration / attendance worksheets
with synthetic data covering today through the next 8 weeks.

Run with:
    python -m scripts.seed_test_data
"""

import logging
import sys
from datetime import datetime, timedelta

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from gspread_dataframe import set_with_dataframe

from app.config import get_settings

log = logging.getLogger(__name__)
logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s: %(message)s")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

WEEKS_AHEAD = 8


def _build_dataset() -> dict[str, pd.DataFrame]:
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    monday_this_week = today - timedelta(days=today.weekday())

    students = pd.DataFrame([
        {"student_id": 1, "name": "Alice Chen",   "parent_contact": "alice_parent@example.com", "gender": "F",
         "date_of_register": "2025-09-01", "referee": "Instagram", "payment_method": "Credit Card"},
        {"student_id": 2, "name": "Bob Patel",    "parent_contact": "bob_parent@example.com",   "gender": "M",
         "date_of_register": "2025-09-15", "referee": "Friend",    "payment_method": "Cash"},
        {"student_id": 3, "name": "Carol Singh",  "parent_contact": "carol_parent@example.com", "gender": "F",
         "date_of_register": "2025-10-02", "referee": "Web",       "payment_method": "Credit Card"},
        {"student_id": 4, "name": "David Kim",    "parent_contact": "david_parent@example.com", "gender": "M",
         "date_of_register": "2026-01-10", "referee": "Sibling",   "payment_method": "Bank Transfer"},
        {"student_id": 5, "name": "Eve Tanaka",   "parent_contact": "eve_parent@example.com",   "gender": "F",
         "date_of_register": "2026-02-22", "referee": "Web",       "payment_method": "Cash"},
    ])

    courses = pd.DataFrame([
        {"course_id": 1, "course_name": "Maths Tutorial",  "active": True},
        {"course_id": 2, "course_name": "Art Studio",      "active": True},
        {"course_id": 3, "course_name": "Piano Lesson",    "active": True},
    ])

    # Patterns: (course_id, weekday-index Mon=0, start_hour, end_hour)
    schedule = [
        (1, 0, 10, 11),   # Maths Mon 10:00-11:00
        (1, 2, 14, 15),   # Maths Wed 14:00-15:00
        (2, 1, 16, 17),   # Art   Tue 16:00-17:00
        (2, 4, 10, 12),   # Art   Fri 10:00-12:00
        (3, 3, 18, 19),   # Piano Thu 18:00-19:00
    ]

    lesson_rows = []
    lesson_id = 1
    for w in range(WEEKS_AHEAD):
        for (cid, wd, sh, eh) in schedule:
            start = monday_this_week + timedelta(weeks=w, days=wd, hours=sh)
            end = monday_this_week + timedelta(weeks=w, days=wd, hours=eh)
            lesson_rows.append({
                "lesson_id": lesson_id,
                "start_datetime": start.strftime("%Y-%m-%d %H:%M:%S"),
                "end_datetime": end.strftime("%Y-%m-%d %H:%M:%S"),
                "course_id": cid,
            })
            lesson_id += 1
    lessons = pd.DataFrame(lesson_rows)

    # Each student is registered for a subset of courses.
    student_courses = {
        1: [1, 2],         # Alice: Maths + Art
        2: [1],            # Bob:   Maths
        3: [2, 3],         # Carol: Art + Piano
        4: [1, 3],         # David: Maths + Piano
        5: [2],            # Eve:   Art
    }

    reg_rows = []
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for student_id, course_ids in student_courses.items():
        for cid in course_ids:
            for _, row in lessons[lessons["course_id"] == cid].iterrows():
                reg_rows.append({
                    "student_id": student_id,
                    "lesson_id": row["lesson_id"],
                    "datetime_of_registration": now_str,
                    "status": "active",
                })
    registrations = pd.DataFrame(reg_rows)

    # Mark attendance for any lesson whose start is in the past (so the demo
    # has 'completed' rows on the student page).
    now = datetime.now()
    att_rows = []
    for r in reg_rows:
        lesson = lessons[lessons["lesson_id"] == r["lesson_id"]].iloc[0]
        start = datetime.strptime(lesson["start_datetime"], "%Y-%m-%d %H:%M:%S")
        if start < now:
            att_rows.append({
                "student_id": r["student_id"],
                "lesson_id": r["lesson_id"],
                "attendance_datetime": lesson["start_datetime"],
            })
    attendance = pd.DataFrame(att_rows)

    return {
        "student": students,
        "course": courses,
        "lesson": lessons,
        "course_registration": registrations,
        "attendance": attendance,
    }


def main() -> int:
    settings = get_settings()
    if not settings.google_sheets_spreadsheet_id:
        log.error("GOOGLE_SHEETS_SPREADSHEET_ID is not set in .env")
        return 1
    if not settings.google_service_account_path.exists():
        log.error("Service account file not found at %s", settings.google_service_account_path)
        return 1

    creds = Credentials.from_service_account_file(str(settings.google_service_account_path), scopes=SCOPES)
    client = gspread.authorize(creds)
    sh = client.open_by_key(settings.google_sheets_spreadsheet_id)

    tables = _build_dataset()

    existing = {ws.title for ws in sh.worksheets()}
    for name, df in tables.items():
        if name in existing:
            sh.del_worksheet(sh.worksheet(name))
        ws = sh.add_worksheet(title=name, rows=str(len(df) + 5), cols=str(max(len(df.columns) + 2, 8)))
        set_with_dataframe(ws, df, include_index=False, resize=True)
        log.info("Wrote %d rows to sheet '%s'", len(df), name)

    log.info("Spreadsheet: https://docs.google.com/spreadsheets/d/%s", settings.google_sheets_spreadsheet_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
