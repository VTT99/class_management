import logging

import pandas as pd
from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_bearer_token
from app.config import get_settings
from app.db import get_conn
from app.models import CalendarGenerationRequest
from app.services.google_calendar import (
    HttpError,
    _build_service,
    build_event_body,
    is_event_changed,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["calendar"], dependencies=[Depends(require_bearer_token)])


def _fetch_lessons_in_window(start_dt: pd.Timestamp, end_dt: pd.Timestamp) -> pd.DataFrame:
    with get_conn(read_only=True) as con:
        return con.execute(
            """
            SELECT s.name AS student_name, s.student_id, l.lesson_id,
                   l.start_datetime, l.end_datetime, c.course_name, c.course_id
            FROM course_registration r
            JOIN lesson l ON r.lesson_id = l.lesson_id
            JOIN student s ON r.student_id = s.student_id
            JOIN course c ON l.course_id = c.course_id
            WHERE r.status = 'active'
              AND strptime(l.start_datetime, '%Y-%m-%d %H:%M:%S') BETWEEN ? AND ?
            ORDER BY l.start_datetime
            """,
            [start_dt.strftime("%Y-%m-%d %H:%M:%S"), end_dt.strftime("%Y-%m-%d %H:%M:%S")],
        ).fetchdf()


def _require_service():
    service = _build_service()
    if service is None:
        raise HTTPException(
            status_code=503,
            detail="Calendar integration is not configured. Set GOOGLE_CALENDAR_ID and provide a service-account key.",
        )
    return service


@router.post("/generate_calendar_events", summary="Wipe and recreate events in the upcoming N months")
def generate_calendar_events(req: CalendarGenerationRequest) -> dict:
    service = _require_service()
    calendar_id = get_settings().google_calendar_id
    start_dt = pd.Timestamp.now(tz="UTC").replace(microsecond=0)
    end_dt = start_dt + relativedelta(months=req.months_ahead)

    try:
        existing = service.events().list(
            calendarId=calendar_id,
            timeMin=start_dt.isoformat().replace("+00:00", "Z"),
            timeMax=end_dt.isoformat().replace("+00:00", "Z"),
            singleEvents=True,
        ).execute()
        for ev in existing.get("items", []):
            try:
                service.events().delete(calendarId=calendar_id, eventId=ev["id"]).execute()
            except HttpError as e:
                log.warning("Failed to delete event %s: %s", ev["id"], e)
    except HttpError as e:
        raise HTTPException(status_code=502, detail=f"Calendar list/delete failed: {e}") from e

    df = _fetch_lessons_in_window(start_dt, end_dt)
    if df.empty:
        return {"message": f"No lessons found in the next {req.months_ahead} month(s).", "events": []}

    course_colors = {cid: str((i % 11) + 1) for i, cid in enumerate(df["course_id"].unique())}

    created = []
    for lesson_id, group in df.groupby("lesson_id"):
        body = build_event_body(group, group.iloc[0]["course_name"], lesson_id, course_colors)
        try:
            ev = service.events().insert(calendarId=calendar_id, body=body).execute()
            created.append({
                "event_id": ev["id"],
                "summary": ev["summary"],
                "start": ev["start"]["dateTime"],
                "end": ev["end"]["dateTime"],
            })
        except HttpError as e:
            log.error("Failed to insert event for lesson %s: %s", lesson_id, e)

    return {
        "message": f"Replaced events: created {len(created)} events for the next {req.months_ahead} month(s).",
        "events": created,
    }


@router.post("/sync_calendar_events", summary="Diff-based sync: only create/update/delete what changed")
def sync_calendar_events(req: CalendarGenerationRequest) -> dict:
    service = _require_service()
    calendar_id = get_settings().google_calendar_id
    start_dt = pd.Timestamp.now(tz="UTC").replace(microsecond=0)
    end_dt = start_dt + relativedelta(months=req.months_ahead)

    df = _fetch_lessons_in_window(start_dt, end_dt)
    course_colors = {cid: str((i % 11) + 1) for i, cid in enumerate(df["course_id"].unique())} if not df.empty else {}
    db_events: dict[str, dict] = {}
    if not df.empty:
        for lesson_id, group in df.groupby("lesson_id"):
            db_events[str(lesson_id)] = build_event_body(
                group, group.iloc[0]["course_name"], lesson_id, course_colors,
            )

    cal_events: dict[str, dict] = {}
    page_token = None
    try:
        while True:
            page = service.events().list(
                calendarId=calendar_id,
                timeMin=start_dt.isoformat(),
                timeMax=end_dt.isoformat(),
                singleEvents=True,
                privateExtendedProperty="lesson_id",
                pageToken=page_token,
            ).execute()
            for ev in page.get("items", []):
                lid = ev["extendedProperties"]["private"]["lesson_id"]
                cal_events[lid] = ev
            page_token = page.get("nextPageToken")
            if not page_token:
                break
    except HttpError as e:
        raise HTTPException(status_code=502, detail=f"Calendar list failed: {e}") from e

    to_create, to_update, to_delete = [], [], []
    for lid, body in db_events.items():
        if lid not in cal_events:
            to_create.append(body)
        elif is_event_changed(cal_events[lid], body):
            to_update.append((cal_events[lid]["id"], body))
    for lid, ev in cal_events.items():
        if lid not in db_events:
            to_delete.append(ev["id"])

    batch = service.new_batch_http_request()

    def _cb(request_id, response, exception):
        if exception:
            log.error("Batch request %s failed: %s", request_id, exception)

    for body in to_create:
        batch.add(service.events().insert(calendarId=calendar_id, body=body), callback=_cb)
    for ev_id, body in to_update:
        batch.add(service.events().update(calendarId=calendar_id, eventId=ev_id, body=body), callback=_cb)
    for ev_id in to_delete:
        batch.add(service.events().delete(calendarId=calendar_id, eventId=ev_id), callback=_cb)
    if to_create or to_update or to_delete:
        try:
            batch.execute()
        except HttpError as e:
            raise HTTPException(status_code=502, detail=f"Batch sync failed: {e}") from e

    return {
        "message": "Calendar synchronization complete.",
        "created": len(to_create),
        "updated": len(to_update),
        "deleted": len(to_delete),
    }
