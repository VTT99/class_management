import logging
from typing import Dict, List

import gspread
from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_bearer_token
from app.config import get_settings
from app.db import get_conn
from app.services.google_sheets import (
    SYNCED_TABLES,
    _client,
    download_table_from_sheet,
    upload_table_to_sheet,
)

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


@router.post("/download_sheets_to_db", summary="Replace every DuckDB table with the contents of the matching Google Sheet")
def download_sheets_to_db() -> Dict:
    """Inverse of /upload_db_to_sheets. Destructive — drops each table and
    recreates it from the sheet's contents. Use when you want the server
    DB to match what's in the Sheet (e.g. after editing the Sheet manually,
    or after a teammate uploaded changes)."""
    settings = get_settings()
    client = _client()
    if client is None:
        raise HTTPException(
            status_code=503,
            detail="Google Sheets not configured (need GOOGLE_SHEETS_SPREADSHEET_ID and a service-account key).",
        )

    loaded: List[Dict] = []
    skipped: List[Dict] = []
    with get_conn(read_only=False) as con:
        for table in SYNCED_TABLES:
            try:
                df = download_table_from_sheet(client, settings.google_sheets_spreadsheet_id, table)
            except gspread.WorksheetNotFound:
                skipped.append({"table": table, "reason": "Worksheet not found in spreadsheet."})
                continue
            except Exception as e:
                skipped.append({"table": table, "reason": f"Sheet read failed: {e!r}"})
                continue

            if df.empty:
                skipped.append({"table": table, "reason": "Sheet has no rows."})
                continue

            try:
                con.execute(f"DROP TABLE IF EXISTS {table}")
                con.register("__import_df", df)
                con.execute(f"CREATE TABLE {table} AS SELECT * FROM __import_df")
                con.unregister("__import_df")
                loaded.append({"table": table, "rows": int(len(df))})
            except Exception as e:
                skipped.append({"table": table, "reason": f"DB write failed: {e!r}"})

    return {
        "message": f"Pulled {len(loaded)} table(s) from Google Sheets into the DB.",
        "spreadsheet": f"https://docs.google.com/spreadsheets/d/{settings.google_sheets_spreadsheet_id}",
        "loaded": loaded,
        "skipped": skipped,
    }
