# Tutorial Center — Usage Guide

## Prerequisites

- Python 3.11 or later.
- A Google Cloud project with the **Sheets API** and **Calendar API** enabled.
- A service-account JSON key from that project.
- The target Google Calendar shared with the service-account email as an
  editor.
- The Google Sheet shared with the service-account email as a viewer (or
  editor, if you want to use `seed_test_data.py`).

## First-time setup

1. **Clone or copy this repo** to your machine.
2. **Create a virtualenv and install dependencies**:
    ```bash
    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    ```
3. **Configure environment variables**: copy `.env.example` to `.env` and
   fill in:
    - `GOOGLE_CALENDAR_ID` — calendar ID where lesson events will go.
    - `GOOGLE_SHEETS_SPREADSHEET_ID` — spreadsheet ID for ETL.
    - `API_BEARER_TOKEN` — optional. If set, all endpoints require
      `Authorization: Bearer <token>`.
4. **Drop the service-account JSON** in `secrets/service_account.json` (it
   is gitignored).
5. **Hydrate the DB** from Google Sheets:
    ```bash
    python -m scripts.download_sheet_to_db
    ```
   If you already have `data/tutorial_center.duckdb`, you can skip this.

## Running

```bash
uvicorn app.main:app --reload
```

- UI: <http://127.0.0.1:8000/>
- Swagger UI: <http://127.0.0.1:8000/docs>
- Health probe: <http://127.0.0.1:8000/health>

## API reference

All bodies are JSON. Errors return `{"detail": "..."}` with the right HTTP
status code.

### `POST /student_data`

Request:
```json
{ "student_id": 1 }
```
Response:
```json
{
  "student": { "student_id": 1, "name": "...", ... },
  "course_summary": {
    "1": { "course_name": "Math class", "completed": 3, "uncomplete": 1,
           "not_yet_complete": 6, "total": 10 }
  },
  "lessons": { "1": [ { "lesson_id": "...", "start_datetime": "...",
                        "participation_status": "attended",
                        "lesson_status": "completed" }, ... ] }
}
```

### `POST /add_student`  →  `201 Created`

```json
{ "name": "Charlie", "parent_contact": "c@x", "gender": "Other",
  "payment_method": "Cash", "referee": null }
```
- `gender` must be one of `F`, `M`, `Other`.
- Returns the auto-generated `student_id`.

### `GET /search_courses?course_name_partial=Math`

Returns `[{ "course_id": …, "course_name": …, "available_start_times": [...] }]`.
Empty list if nothing matches.

### `POST /register_lessons`

```json
{ "student_id": 1, "course_id": 2, "day_of_week": "Monday",
  "start_time": "18:00", "number_of_lessons": 10,
  "first_lesson_date": null }
```
- `day_of_week` must be a full day name (`Monday` … `Sunday`).
- If fewer than `number_of_lessons` matching lessons exist, returns 400 with
  `error_code: INSUFFICIENT_LESSONS_FOUND`.

### `GET /lesson_participants?lesson_id=42`

Returns the students registered for a lesson, sorted by name.

### `POST /mark_attendance`

```json
{ "lesson_id": 42, "student_id": 1 }
```
- 404 if the lesson does not exist.
- 409 if the student is not registered for that lesson.
- Idempotent: marking the same student twice is a no-op.

### `POST /mark_attendance_bulk`

```json
{ "lesson_id": 42, "student_ids": [1, 2, 3] }
```
Returns `marked_count`, the list of students marked, and a list of any
failures (e.g. unregistered students).

### `POST /sync_calendar_events` (recommended)

```json
{ "months_ahead": 1 }
```
Diff-based sync: only creates new events, updates changed ones, and deletes
events that no longer have a matching lesson. Safe to re-run.

### `POST /generate_calendar_events`

Wipes all events in the window and recreates them. Destructive; the UI asks
for confirmation.

### `GET /students/{student_id}/lessons.csv`

Streams a CSV of every lesson the student is registered for, with status.

### `GET /health`

```json
{ "status": "ok", "db": "ok", "calendar_configured": true }
```

## Database schema

DuckDB tables loaded from Google Sheets:

| table | columns |
|---|---|
| `student` | `student_id`, `name`, `parent_contact`, `gender`, `date_of_register`, `referee`, `payment_method` |
| `course` | `course_id`, `course_name`, `active` |
| `lesson` | `lesson_id`, `start_datetime`, `end_datetime`, `course_id` |
| `course_registration` | `student_id`, `lesson_id`, `datetime_of_registration`, `status` (`active` / `cancel`), plus optional `registration_id` and `course_id` depending on seed source |
| `attendance` | `attendance_id`, `student_id`, `lesson_id`, `attendance_datetime` |

`start_datetime` / `end_datetime` are stored as strings in
`%Y-%m-%d %H:%M:%S`. The queries `strptime` them as needed.

## Running the tests

```bash
pytest
```

Tests spin up a fresh DuckDB in a tmp dir for each session — they do not
touch your real data file and they do not call Google APIs.

## Refreshing data

```bash
python -m scripts.download_sheet_to_db
```

Pulls every worksheet listed in the script into the local DuckDB, dropping
and recreating each table. Reads paths from `.env`.

## Seeding test data (writes to Google Sheets)

```bash
python -m scripts.seed_test_data
```

Creates two students (Alice, Bob), two courses, 28 weekly lessons each,
ten registrations each, and a handful of attendance records. Will **delete**
existing worksheets of the same name in the configured spreadsheet.

## Troubleshooting

- **`FileNotFoundError: DuckDB file not found`** — run
  `python -m scripts.download_sheet_to_db` or copy a `.duckdb` file into
  `data/`.
- **`Calendar integration is not configured` (503)** — `.env` is missing
  `GOOGLE_CALENDAR_ID`, or `secrets/service_account.json` is missing.
- **`Insufficient permissions` from Google** — the service-account email
  needs to be added to the calendar and sheet with editor / viewer access.
- **`HttpError 403` from Calendar** — quota exceeded; back off and retry.
- **CORS errors in the browser** — the bundled UI is served by the same
  process, so it should not hit CORS. If you serve the UI from a different
  origin, add that origin to `app/main.py`'s `CORSMiddleware`.

## What changed from the old code

- One FastAPI app instead of `main.py` / `main2.py` / `main3.py`.
- One frontend (`templates/index.html` + `static/`) instead of `main.html` /
  `main2.html` / `main4.html`.
- All SQL is parameterized (no f-string injection).
- The stray `breakpoint()` in `sync_calendar_events` is gone.
- Pydantic validates inputs (gender, day-of-week, time, IDs).
- A real bearer-token guard (off by default) for when the API is exposed.
- A `/health` endpoint, CSV export, and bulk-attendance endpoint.
- Tests run against a temp DuckDB without touching Google APIs.
