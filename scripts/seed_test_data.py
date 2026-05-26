"""Seed a Google Sheet with a small synthetic dataset for development.

Migrated off the deprecated oauth2client library.

Run with:
    python -m scripts.seed_test_data
"""

import logging
import sys

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

WEEKDAYS = {"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6}


def _build_students() -> pd.DataFrame:
    return pd.DataFrame({
        "student_id": [1, 2],
        "name": ["Alice", "Bob"],
        "parent_contact": ["alice_parent@gmail.com", "bob_parent@gmail.com"],
        "gender": ["F", "M"],
        "date_of_register": [pd.Timestamp.today().normalize()] * 2,
        "referee": ["Instagram", "Friend"],
        "payment_method": ["Credit Card", "Cash"],
    })


def _build_courses() -> pd.DataFrame:
    return pd.DataFrame({
        "course_id": [1, 2],
        "course_name": ["Art class", "Math class"],
        "active": [True, True],
    })


def _build_lessons() -> pd.DataFrame:
    rows = []
    today = pd.Timestamp.today().normalize()
    for course_id, weekday_name in [(1, "Monday"), (2, "Thursday")]:
        target = WEEKDAYS[weekday_name]
        first = today + pd.DateOffset(days=(target - today.weekday()) % 7)
        for i in range(28):
            start = first + pd.DateOffset(weeks=i)
            end = start + pd.Timedelta(hours=1, minutes=30)
            rows.append({
                "lesson_id": f"{course_id}_{i+1}",
                "start_datetime": start.strftime("%Y-%m-%d %H:%M:%S"),
                "end_datetime": end.strftime("%Y-%m-%d %H:%M:%S"),
                "course_id": course_id,
            })
    return pd.DataFrame(rows)


def _build_registrations() -> pd.DataFrame:
    rows = []
    for i in range(10):
        rows.append({"registration_id": f"A_{i+1}", "student_id": 1, "lesson_id": f"1_{i+1}",
                     "datetime_of_registration": pd.Timestamp.now(), "status": "active"})
        rows.append({"registration_id": f"B_{i+1}", "student_id": 2, "lesson_id": f"2_{i+1}",
                     "datetime_of_registration": pd.Timestamp.now(), "status": "active"})
    return pd.DataFrame(rows)


def _build_attendance(lessons: pd.DataFrame) -> pd.DataFrame:
    out = []
    plan = [(1, [1, 2, 3]), (2, [1, 2])]
    for student_id, lesson_ix in plan:
        for i in lesson_ix:
            lid = f"{student_id}_{i}"
            ts = lessons.loc[lessons["lesson_id"] == lid, "start_datetime"].values[0]
            out.append({
                "attendance_id": f"{'A' if student_id == 1 else 'B'}_{i}",
                "student_id": student_id,
                "lesson_id": lid,
                "attendance_datetime": ts,
            })
    return pd.DataFrame(out)


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

    lessons = _build_lessons()
    tables = {
        "student": _build_students(),
        "course": _build_courses(),
        "lesson": lessons,
        "course_registration": _build_registrations(),
        "attendance": _build_attendance(lessons),
    }

    existing = {ws.title for ws in sh.worksheets()}
    for name, df in tables.items():
        if name in existing:
            sh.del_worksheet(sh.worksheet(name))
        ws = sh.add_worksheet(title=name, rows=str(len(df) + 5), cols=str(len(df.columns)))
        set_with_dataframe(ws, df)
        log.info("Wrote %d rows to sheet '%s'", len(df), name)

    log.info("Upload complete: https://docs.google.com/spreadsheets/d/%s", settings.google_sheets_spreadsheet_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
