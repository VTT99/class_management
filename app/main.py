import logging
from functools import lru_cache

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import REPO_ROOT, get_settings
from app.db import get_conn
from app.routers import attendance, calendar, courses, registration, sheets, students

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
    root_path=settings.root_path,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(students.router)
app.include_router(courses.router)
app.include_router(registration.router)
app.include_router(attendance.router)
app.include_router(calendar.router)
app.include_router(sheets.router)

if settings.serve_frontend:
    app.mount("/static", StaticFiles(directory=str(REPO_ROOT / "static")), name="static")

    @lru_cache(maxsize=1)
    def _rendered_index() -> str:
        html = (REPO_ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        return html.replace("{{ root_path }}", settings.root_path)

    @app.get("/", include_in_schema=False, response_class=HTMLResponse)
    def index() -> HTMLResponse:
        return HTMLResponse(_rendered_index())


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
