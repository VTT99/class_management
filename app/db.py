from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import duckdb

from app.config import get_settings


@contextmanager
def get_conn(read_only: bool = True) -> Iterator[duckdb.DuckDBPyConnection]:
    path: Path = get_settings().duckdb_path
    if not path.exists():
        raise FileNotFoundError(
            f"DuckDB file not found at {path}. "
            "Run `python -m scripts.download_sheet_to_db` to create it."
        )
    con = duckdb.connect(str(path), read_only=read_only)
    try:
        yield con
    finally:
        con.close()


def ensure_schema() -> None:
    """Create tables this app needs that may not be in older DuckDB files.
    Safe to call repeatedly. Reads the current DB path from settings."""
    path = get_settings().duckdb_path
    if not path.exists():
        return  # caller should hydrate the DB first; nothing to migrate
    con = duckdb.connect(str(path), read_only=False)
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS purchase (
                purchase_id BIGINT PRIMARY KEY,
                student_id BIGINT NOT NULL,
                course_id BIGINT NOT NULL,
                count INTEGER NOT NULL,
                payment_method VARCHAR,
                purchase_datetime VARCHAR
            )
            """
        )
    finally:
        con.close()
