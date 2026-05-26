"""Pure helper: assign a human-readable status to each lesson row."""

from typing import Optional

import pandas as pd


def label_lesson_status(participation_status: Optional[str], start_datetime, now: pd.Timestamp) -> str:
    start_time = pd.to_datetime(start_datetime, errors="coerce")
    if pd.isna(start_time):
        return "unknown"
    if participation_status == "attended":
        return "completed"
    if (participation_status in ("unattended", None, "")) and start_time < now:
        return "uncomplete"
    return "not-yet-complete"
