# Tutorial Center

A small FastAPI + DuckDB app for managing tutorial-center students, lessons,
attendance, and Google Calendar events. The frontend is served by FastAPI as
static HTML / JS / CSS — no Node toolchain required.

## Quick start

```bash
cd ~/class_management

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Copy & fill in your env values
cp .env.example .env
$EDITOR .env

# Drop your Google service-account JSON here (already gitignored):
#   secrets/service_account.json

# (Optional) refresh DuckDB from Google Sheets:
python -m scripts.download_sheet_to_db

# Run the server:
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000/> for the UI, or <http://127.0.0.1:8000/docs> for
the interactive API docs.

## Repo layout

```
app/         FastAPI app (routers, models, db helpers, services)
static/      JS + CSS served at /static/
templates/   HTML served at /
scripts/     ETL: download_sheet_to_db.py, seed_test_data.py
tests/       pytest suite
data/        DuckDB file (gitignored)
secrets/     Service-account JSON (gitignored)
docs/        Long-form usage and API reference
```

See [`docs/USAGE.md`](docs/USAGE.md) for the full reference, including the
endpoint list, database schema, and troubleshooting.
