import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import REPO_ROOT, get_settings
from app.db import get_conn
from app.routers import attendance, calendar, courses, registration, students

settings = get_settings()
logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

app = FastAPI(
    title="Tutorial Center API",
    description="Manage students, lessons, attendance and Google Calendar events for a tutorial center.",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(students.router)
app.include_router(courses.router)
app.include_router(registration.router)
app.include_router(attendance.router)
app.include_router(calendar.router)

app.mount("/static", StaticFiles(directory=str(REPO_ROOT / "static")), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(REPO_ROOT / "templates" / "index.html")


@app.get("/health", tags=["meta"])
def health() -> dict:
    """Lightweight health probe: confirms the DB is reachable."""
    info = {"status": "ok", "db": "unknown", "calendar_configured": bool(settings.google_calendar_id)}
    try:
        with get_conn(read_only=True) as con:
            con.execute("SELECT 1").fetchone()
        info["db"] = "ok"
    except FileNotFoundError as e:
        info["status"] = "degraded"
        info["db"] = f"missing: {e}"
    except Exception as e:  # pragma: no cover
        info["status"] = "degraded"
        info["db"] = f"error: {e!r}"
    return info
