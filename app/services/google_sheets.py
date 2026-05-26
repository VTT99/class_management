"""Google Sheets helpers: pull worksheets into the DB and push them back."""

import logging
from typing import List, Optional

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from gspread_dataframe import set_with_dataframe

from app.config import get_settings

log = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Tables we sync. Order matters slightly for download (foreign-key-ish);
# for upload, order doesn't matter beyond being deterministic in logs.
SYNCED_TABLES: List[str] = [
    "student",
    "course",
    "lesson",
    "course_registration",
    "attendance",
]


def _client() -> Optional[gspread.Client]:
    settings = get_settings()
    if not settings.google_sheets_spreadsheet_id:
        return None
    if not settings.google_service_account_path.exists():
        log.warning("Service account file missing at %s.", settings.google_service_account_path)
        return None
    creds = Credentials.from_service_account_file(str(settings.google_service_account_path), scopes=SCOPES)
    return gspread.authorize(creds)


def upload_table_to_sheet(client: gspread.Client, spreadsheet_id: str, name: str, df: pd.DataFrame) -> None:
    sh = client.open_by_key(spreadsheet_id)
    titles = {ws.title for ws in sh.worksheets()}
    if name in titles:
        ws = sh.worksheet(name)
        ws.clear()
    else:
        # Some buffer rows/cols so set_with_dataframe doesn't complain.
        ws = sh.add_worksheet(title=name, rows=str(max(len(df) + 5, 50)), cols=str(max(len(df.columns) + 2, 10)))
    set_with_dataframe(ws, df, include_index=False, resize=True)


def download_table_from_sheet(client: gspread.Client, spreadsheet_id: str, name: str) -> pd.DataFrame:
    sh = client.open_by_key(spreadsheet_id)
    ws = sh.worksheet(name)
    return pd.DataFrame(ws.get_all_records())
