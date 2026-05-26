import logging
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_bearer_token
from app.config import get_settings
from app.db import get_conn
from app.services.google_sheets import SYNCED_TABLES, _client, upload_table_to_sheet

log = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["sheets"], dependencies=[Depends(require_bearer_token)])


@router.post("/upload_db_to_sheets", summary="Push every DuckDB table back to its matching Google Sheet")
def upload_db_to_sheets() -> Dict:
    settings = get_settings()
    client = _client()
    if client is None:
        raise HTTPException(
            status_code=503,
            detail="Google Sheets not configured (need GOOGLE_SHEETS_SPREADSHEET_ID and a service-account key).",
        )

    pushed: List[Dict] = []
    skipped: List[Dict] = []
    with get_conn(read_only=True) as con:
        for table in SYNCED_TABLES:
            try:
                df = con.execute(f"SELECT * FROM {table}").fetchdf()
            except Exception as e:
                skipped.append({"table": table, "reason": f"DB read failed: {e!r}"})
                continue
            try:
                upload_table_to_sheet(client, settings.google_sheets_spreadsheet_id, table, df)
                pushed.append({"table": table, "rows": int(len(df))})
            except Exception as e:
                skipped.append({"table": table, "reason": f"Sheet write failed: {e!r}"})

    return {
        "message": f"Pushed {len(pushed)} table(s) to Google Sheets.",
        "spreadsheet": f"https://docs.google.com/spreadsheets/d/{settings.google_sheets_spreadsheet_id}",
        "pushed": pushed,
        "skipped": skipped,
    }
