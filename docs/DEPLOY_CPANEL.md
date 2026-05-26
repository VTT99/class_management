# Deploying on shared hosting via cPanel "Setup Python App"

This is for cPanel-based shared hosts that include **Phusion Passenger**
(visible in cPanel as **Setup Python App** / **Python Selector** /
**Application Manager**). The result will be the app served under
`https://your-domain/class_management/`, with the same UI and API as the
local build.

## How the pieces fit together

```
Internet
   │
   ▼  https://your-domain/class_management/*
+--------+        +-----------+        +-------------------+
| Apache | -----> | Passenger | -----> | passenger_wsgi.py |
+--------+        +-----------+        |  └─ a2wsgi wraps  |
                                       |     FastAPI       |
                                       +-------------------+
                                              │
                                              ▼
                                       data/tutorial_center.duckdb
                                       secrets/service_account.json
```

- **Apache** terminates HTTPS and routes the URL.
- **Passenger** keeps a Python interpreter alive between requests and
  restarts it on demand (via `tmp/restart.txt`).
- **`passenger_wsgi.py`** is the entry point cPanel calls. It wraps our
  ASGI app with `a2wsgi` so the WSGI ↔ ASGI handoff works.

You don't run `uvicorn` yourself on shared hosting — Passenger does the
process management.

---

## Step-by-step

### 1. Upload the code

In cPanel → **File Manager** (or via SSH if you have it), put the repo at:

```
~/class_management/
```

(NOT inside `~/public_html/`. cPanel will create a symlink from
`~/public_html/class_management` for you in step 4.)

Via SSH this looks like:

```bash
cd ~
git clone https://github.com/VTT99/class_management.git
```

### 2. Configure `.env`

```bash
cd ~/class_management
cp .env.example .env
nano .env
```

Set at least:

```
DUCKDB_FILE=data/tutorial_center.duckdb
GOOGLE_SERVICE_ACCOUNT_FILE=secrets/service_account.json
GOOGLE_CALENDAR_ID=...your calendar...
GOOGLE_SHEETS_SPREADSHEET_ID=...your sheet...
TIMEZONE=Asia/Hong_Kong
LOG_LEVEL=INFO

# Must match the cPanel Application URL sub-path:
ROOT_PATH=/class_management

# Strongly recommended on shared hosting:
API_BEARER_TOKEN=some-long-random-string
```

### 3. Upload the service-account key

Upload your Google service-account JSON to
`~/class_management/secrets/service_account.json`. Set strict permissions:

```bash
chmod 600 ~/class_management/secrets/service_account.json
```

If you don't have the DuckDB file yet, you'll regenerate it in step 6.

### 4. Create the Python app in cPanel

cPanel main page → **Software → Setup Python App** (or
**Python Selector** / **Application Manager**) → **Create Application**.

Fill in:

| Field | Value |
|---|---|
| Python version | 3.11 (or 3.12) |
| Application root | `class_management` |
| Application URL | `your-domain.com` / `class_management` |
| Application startup file | `passenger_wsgi.py` |
| Application entry point | `application` |
| Passenger log file | leave default |

Click **Create**. cPanel:

- creates a virtualenv at `~/virtualenv/class_management/3.11/`,
- writes an `.htaccess` in `~/public_html/class_management/` that routes
  through Passenger,
- prints a command like
  `source /home/USER/virtualenv/class_management/3.11/bin/activate && cd /home/USER/class_management`.
  Save that — you'll use it.

### 5. Install dependencies

In the cPanel app's UI there's an **Install Packages** / **Run pip install**
button. Pick `requirements.txt` and run it.

If you prefer SSH:

```bash
source ~/virtualenv/class_management/3.11/bin/activate
cd ~/class_management
pip install -r requirements.txt
```

### 6. Hydrate the DuckDB

```bash
source ~/virtualenv/class_management/3.11/bin/activate
cd ~/class_management
python -m scripts.download_sheet_to_db
```

This pulls all sheets from `GOOGLE_SHEETS_SPREADSHEET_ID` into
`data/tutorial_center.duckdb`.

If you already have a `tutorial_center.duckdb` from your laptop, just SFTP
it into `~/class_management/data/`.

### 7. Restart the app

After any code change, .env change, or `pip install`, restart by touching:

```bash
mkdir -p ~/class_management/tmp
touch ~/class_management/tmp/restart.txt
```

cPanel's "Setup Python App" UI also has a **Restart** button — same effect.

### 8. Verify

In a browser:

- **UI:** `https://your-domain/class_management/`
- **API docs:** `https://your-domain/class_management/docs`
- **Health:** `https://your-domain/class_management/health`

The health badge in the top-right should turn green.

From the shell, the same checks via curl:

```bash
curl -s https://your-domain/class_management/health
```

---

## Day-to-day

- **Tail Passenger log:** in the cPanel UI, the application's page lists a
  log path; otherwise `tail -f ~/class_management/passenger.log` (or
  similar — your host's docs name the file).
- **Restart:** `touch ~/class_management/tmp/restart.txt`.
- **Update code:**
  ```bash
  cd ~/class_management && git pull
  source ~/virtualenv/class_management/3.11/bin/activate
  pip install -r requirements.txt
  touch tmp/restart.txt
  ```

## Troubleshooting

- **500 Internal Server Error** — the Python app failed to import. Look at
  the Passenger log; almost always a missing dep or wrong Python version.
  Run `python -c "import app.main"` in the activated venv to see the
  traceback locally on the server.
- **404 from Apache, never reaches the app** — `Application URL` in cPanel
  doesn't match what you're visiting, or the `.htaccess` in
  `~/public_html/class_management/` is missing. Try deleting the app and
  re-creating it.
- **Calendar 503 "not configured"** — `.env` is missing `GOOGLE_CALENDAR_ID`,
  or `secrets/service_account.json` isn't readable by your user.
- **`PermissionError: data/tutorial_center.duckdb`** — DuckDB needs write
  access. `chmod -R u+rw ~/class_management/data`.
- **App caches old code after `git pull`** — you forgot to
  `touch tmp/restart.txt`. Passenger keeps the old interpreter alive
  otherwise.
- **`ModuleNotFoundError: a2wsgi`** — you skipped step 5, or the cPanel
  virtualenv isn't the one running. Activate it explicitly and `pip
  install -r requirements.txt`.

## Security notes

- **Always set `API_BEARER_TOKEN`** on shared hosting. Without it, anyone
  on the internet can call `/add_student`, `/mark_attendance`, calendar
  endpoints, etc.
- Make sure `secrets/service_account.json` lives outside `~/public_html/`
  (it does by default in this layout) and has mode `600`.
- `.env` similarly — never inside `public_html`.
- DuckDB has no auth, so don't expose it directly. The app is the only way
  in.
