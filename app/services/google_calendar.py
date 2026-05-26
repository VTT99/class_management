"""Google Calendar helpers extracted from main3.py."""

import logging
from typing import Any, Optional

import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.config import get_settings

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]

# Marker stored on every event we create. Used to filter
# `events.list` results to only events owned by this app.
APP_TAG_KEY = "app"
APP_TAG_VALUE = "class_management"
APP_TAG_FILTER = f"{APP_TAG_KEY}={APP_TAG_VALUE}"


def _build_service() -> Optional[Any]:
    settings = get_settings()
    if not settings.google_calendar_id:
        return None
    if not settings.google_service_account_path.exists():
        log.warning(
            "Service account file %s not found; calendar features disabled.",
            settings.google_service_account_path,
        )
        return None
    creds = service_account.Credentials.from_service_account_file(
        str(settings.google_service_account_path), scopes=SCOPES,
    )
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def build_event_body(group: pd.DataFrame, course_name: str, lesson_id, course_colors: dict) -> dict:
    students = "\n".join(
        f"{str(row['student_id']).ljust(12)}, {row['student_name']}" for _, row in group.iterrows()
    )
    start_dt = pd.to_datetime(group.iloc[0]["start_datetime"])
    end_dt = pd.to_datetime(group.iloc[0]["end_datetime"])
    course_id = group.iloc[0]["course_id"]
    first_name = group.iloc[0]["student_name"]
    summary = f"{course_name} - {first_name}"
    if len(group) > 1:
        summary += " (and others)"

    tz = get_settings().timezone
    return {
        "summary": summary,
        "description": (
            f"Lesson ID: {lesson_id}\n"
            "------------\n"
            "Student ID, Student Name\n"
            f"{students}"
        ),
        "start": {"dateTime": start_dt.isoformat(), "timeZone": tz},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": tz},
        "colorId": course_colors.get(course_id),
        "extendedProperties": {
            "private": {
                "lesson_id": str(lesson_id),
                APP_TAG_KEY: APP_TAG_VALUE,
            },
        },
    }


def is_event_changed(cal_event: dict, db_event_body: dict) -> bool:
    return (
        cal_event.get("summary") != db_event_body["summary"]
        or cal_event.get("description") != db_event_body["description"]
        or pd.to_datetime(cal_event["start"]["dateTime"]).isoformat()
        != db_event_body["start"]["dateTime"]
        or pd.to_datetime(cal_event["end"]["dateTime"]).isoformat()
        != db_event_body["end"]["dateTime"]
        or cal_event.get("colorId") != db_event_body["colorId"]
    )


__all__ = [
    "_build_service",
    "build_event_body",
    "is_event_changed",
    "HttpError",
    "APP_TAG_FILTER",
]
