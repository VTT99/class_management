"""Pytest fixtures: build a fresh DuckDB in a tmp dir and point app.config at it."""

import os
from pathlib import Path

import duckdb
import pandas as pd
import pytest


@pytest.fixture()
def tmp_db(tmp_path: Path) -> Path:
    """Create a tutorial_center.duckdb populated with a tiny schema."""
    db_path = tmp_path / "test.duckdb"
    con = duckdb.connect(str(db_path))

    con.execute("""
        CREATE TABLE student (
            student_id INTEGER PRIMARY KEY,
            name VARCHAR,
            parent_contact VARCHAR,
            gender VARCHAR,
            date_of_register DATE,
            referee VARCHAR,
            payment_method VARCHAR
        )
    """)
    con.execute("CREATE TABLE course (course_id INTEGER PRIMARY KEY, course_name VARCHAR, active BOOLEAN)")
    con.execute("""
        CREATE TABLE lesson (
            lesson_id INTEGER PRIMARY KEY,
            start_datetime VARCHAR,
            end_datetime VARCHAR,
            course_id INTEGER
        )
    """)
    con.execute("""
        CREATE TABLE course_registration (
            student_id INTEGER,
            lesson_id INTEGER,
            datetime_of_registration TIMESTAMP,
            status VARCHAR
        )
    """)
    con.execute("""
        CREATE TABLE attendance (
            attendance_id VARCHAR,
            student_id INTEGER,
            lesson_id INTEGER,
            attendance_datetime VARCHAR
        )
    """)

    # seed
    con.execute("INSERT INTO student VALUES (1, 'Alice', 'alice@x', 'F', '2025-01-01', 'web', 'Cash')")
    con.execute("INSERT INTO student VALUES (2, 'Bob',   'bob@x',   'M', '2025-01-01', NULL,  'Cash')")
    con.execute("INSERT INTO course VALUES (1, 'Math class', TRUE)")
    con.execute("INSERT INTO course VALUES (2, 'Art class',  TRUE)")

    next_month = pd.Timestamp.now() + pd.Timedelta(days=14)
    yesterday = pd.Timestamp.now() - pd.Timedelta(days=1)
    last_week = pd.Timestamp.now() - pd.Timedelta(days=7)

    def lesson_row(lid, start, end, course_id=1):
        con.execute(
            "INSERT INTO lesson VALUES (?, ?, ?, ?)",
            [lid, start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S"), course_id],
        )

    lesson_row(101, last_week, last_week + pd.Timedelta(hours=1))
    lesson_row(102, yesterday, yesterday + pd.Timedelta(hours=1))
    lesson_row(103, next_month, next_month + pd.Timedelta(hours=1))
    # generate 10 weekly Mondays in the future at 09:00 for the register flow
    base = pd.Timestamp.now().normalize() + pd.Timedelta(days=(0 - pd.Timestamp.now().weekday()) % 7)
    for i in range(10):
        start = base + pd.Timedelta(days=7 * i, hours=9)
        end = start + pd.Timedelta(hours=1)
        lesson_row(200 + i, start, end)

    con.execute("INSERT INTO course_registration VALUES (1, 101, current_timestamp, 'active')")
    con.execute("INSERT INTO course_registration VALUES (1, 102, current_timestamp, 'active')")
    con.execute(
        "INSERT INTO attendance VALUES (?, 1, 101, ?)",
        ["att_1", last_week.strftime("%Y-%m-%d %H:%M:%S")],
    )

    con.close()
    return db_path


@pytest.fixture()
def client(tmp_db, monkeypatch):
    """Configure the app to use the temp DB and return a TestClient."""
    monkeypatch.setenv("DUCKDB_FILE", str(tmp_db))
    monkeypatch.setenv("API_BEARER_TOKEN", "")
    # Bust cached settings so the new env vars are picked up.
    from app import config
    config.get_settings.cache_clear()

    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)
