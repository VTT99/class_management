"""Pull all configured worksheets from Google Sheets into the local DuckDB file.

Run with:
    python -m scripts.download_sheet_to_db
"""

import logging
import sys

import duckdb
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

from app.config import get_settings

log = logging.getLogger(__name__)
logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s: %(message)s")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
SHEET_NAMES = [
    "student",
    "lesson",
    "attendance",
    "course",
    "course_registration",
    "lesson_participation_status",
]


def main() -> int:
    settings = get_settings()
    if not settings.google_sheets_spreadsheet_id:
        log.error("GOOGLE_SHEETS_SPREADSHEET_ID is not set in .env")
        return 1
    if not settings.google_service_account_path.exists():
        log.error("Service account file not found at %s", settings.google_service_account_path)
        return 1

    settings.duckdb_path.parent.mkdir(parents=True, exist_ok=True)

    creds = Credentials.from_service_account_file(str(settings.google_service_account_path), scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(settings.google_sheets_spreadsheet_id)

    con = duckdb.connect(str(settings.duckdb_path))
    try:
        for name in SHEET_NAMES:
            try:
                ws = sh.worksheet(name)
            except gspread.WorksheetNotFound:
                log.warning("Sheet '%s' not found, skipping.", name)
                continue
            records = ws.get_all_records()
            df = pd.DataFrame(records)
            if df.empty:
                log.warning("Sheet '%s' is empty, skipping.", name)
                continue
            con.execute(f"DROP TABLE IF EXISTS {name}")
            con.register("__import_df", df)
            con.execute(f"CREATE TABLE {name} AS SELECT * FROM __import_df")
            con.unregister("__import_df")
            log.info("Loaded %d rows into '%s'", len(df), name)

        tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
        log.info("Tables in DuckDB: %s", tables)
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
