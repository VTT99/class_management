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
