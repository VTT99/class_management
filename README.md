# Tutorial Center

A small FastAPI + DuckDB app for managing tutorial-center students, lessons,
attendance, and Google Calendar events. The frontend is plain HTML / JS /
CSS served by the same FastAPI process — no Node toolchain.

```
GitHub:    https://github.com/VTT99/class_management
Repo path: ~/class_management   (local)
           /opt/class_management (server)
```

Four supported environments — the code is identical, only `.env` and the
process manager differ:

| Where                          | Runner             | URL                                       | Notes |
| ------------------------------ | ------------------ | ----------------------------------------- | --- |
| Laptop dev                     | `uvicorn --reload` | `http://127.0.0.1:8000/`                  | `ROOT_PATH=` empty |
| VPS (your own Ubuntu box)      | systemd + Caddy    | `https://test.com/class_management/`      | `ROOT_PATH=/class_management` |
| Shared hosting (cPanel)        | Phusion Passenger  | `https://your-domain/class_management/`   | `ROOT_PATH=/class_management` |
| Static-only host + backend elsewhere | Apache + remote uvicorn | `https://your-domain/class_management/`   | Frontend in `public_html`, backend on a VPS / PaaS |

---

## Running locally

### One-time setup

```bash
git clone https://github.com/VTT99/class_management.git ~/class_management
cd ~/class_management

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
$EDITOR .env       # fill in Google Calendar / Sheets values; leave ROOT_PATH empty
```

Drop your Google service-account JSON at `secrets/service_account.json`
(the path is already gitignored).

If you don't have a `data/tutorial_center.duckdb` yet, pull one from
Google Sheets:

```bash
python -m scripts.download_sheet_to_db
```

### Start the backend

```bash
cd ~/class_management
source .venv/bin/activate
uvicorn app.main:app --reload
```

Reload-on-change is on; uvicorn listens on `127.0.0.1:8000`.

### Open the frontend

In a browser, open:

- **App:** <http://127.0.0.1:8000/>
- **Interactive API docs:** <http://127.0.0.1:8000/docs>
- **Health probe:** <http://127.0.0.1:8000/health>

The health badge in the top-right corner of the UI should turn green when
the backend is up.

### Run the tests

```bash
pytest
```

Tests use a temp DuckDB; they don't touch your real `data/` file or Google
APIs.

---

## Running on a remote server (production)

Deploy is **uvicorn (systemd)** behind **Caddy** with auto-HTTPS, serving
the app under `https://your-domain/class_management/`. The full step-by-step
lives in [`docs/DEPLOY.md`](docs/DEPLOY.md) — TL;DR:

1. **Provision** an Ubuntu 22.04+ VPS with DNS pointing your domain at it.
2. **Clone** the repo into `/opt/class_management` (as a dedicated
   `class-management` system user), create a `.venv`, and
   `pip install -r requirements.txt`.
3. **Configure `.env`** — set `GOOGLE_CALENDAR_ID`,
   `GOOGLE_SHEETS_SPREADSHEET_ID`, and **`ROOT_PATH=/class_management`**.
   Drop the service-account JSON at `secrets/service_account.json`.
4. **Install the systemd unit:**
   ```bash
   sudo cp /opt/class_management/deploy/class-management.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now class-management
   ```
   uvicorn now listens on `127.0.0.1:8000` with `--root-path
   /class_management`.
5. **Install Caddy and the Caddyfile:**
   ```bash
   sudo apt install -y caddy
   sudo install -m 644 /opt/class_management/deploy/Caddyfile /etc/caddy/Caddyfile
   sudo $EDITOR /etc/caddy/Caddyfile   # change test.com -> your domain
   sudo systemctl reload caddy
   ```
   Caddy auto-issues a Let's Encrypt certificate the first time the domain
   resolves.

### Open the frontend (remote)

From any browser:

- **App:** `https://your-domain/class_management/`
- **API docs:** `https://your-domain/class_management/docs`
- **Health probe:** `https://your-domain/class_management/health`

### Day-to-day server commands

```bash
sudo systemctl status class-management        # is it running?
sudo journalctl -u class-management -f        # tail logs
sudo systemctl restart class-management       # after a config or code change
sudo systemctl reload caddy                   # after editing the Caddyfile
```

### Updating

```bash
sudo -u class-management git -C /opt/class_management pull
sudo -u class-management /opt/class_management/.venv/bin/pip install -r /opt/class_management/requirements.txt
sudo systemctl restart class-management
```

---

## Running on shared hosting (cPanel)

For cPanel-based shared hosts (Namecheap, Bluehost, A2, DreamHost, school
servers with "Setup Python App", …). Full click-by-click walkthrough is in
[`docs/DEPLOY_CPANEL.md`](docs/DEPLOY_CPANEL.md) — TL;DR:

1. SSH or File-Manager the repo to `~/class_management/` (NOT inside
   `~/public_html/`).
2. In `.env`, set `ROOT_PATH=/class_management` and
   `API_BEARER_TOKEN=…` (always token-protect on shared hosting).
3. Upload `secrets/service_account.json` (chmod 600).
4. cPanel → **Setup Python App** → **Create Application**:
    - Application root: `class_management`
    - Application URL: `your-domain.com/class_management`
    - Startup file: `passenger_wsgi.py`
    - Entry point: `application`
5. Run `pip install -r requirements.txt` (cPanel UI button, or `pip` in
   the venv it creates).
6. Hydrate the DB: `python -m scripts.download_sheet_to_db`.
7. Restart: `touch ~/class_management/tmp/restart.txt`.

Open `https://your-domain/class_management/` in a browser.

Day-to-day:

```bash
cd ~/class_management && git pull
source ~/virtualenv/class_management/3.11/bin/activate
pip install -r requirements.txt
touch tmp/restart.txt    # tells Passenger to relaunch the Python process
```

The `passenger_wsgi.py` entry point at the repo root is what cPanel calls;
it wraps the ASGI app with `a2wsgi` so Passenger (which only speaks WSGI)
can talk to FastAPI. You never run `uvicorn` yourself on shared hosting —
Passenger manages the process.

---

## Running with a split frontend (static-only Apache + backend elsewhere)

For hosts that only serve static files from `public_html` (no Setup
Python App, no Passenger). Full walkthrough in
[`docs/DEPLOY_SPLIT.md`](docs/DEPLOY_SPLIT.md) — TL;DR:

1. **Run the backend** anywhere it can — your VPS via
   [`docs/DEPLOY.md`](docs/DEPLOY.md), Fly.io, Render, etc. In its `.env`:
   ```
   SERVE_FRONTEND=false
   ALLOWED_ORIGINS=https://your-domain.example
   API_BEARER_TOKEN=<long-random-string>
   ```
2. **Build the static bundle** on your laptop:
   ```bash
   python -m scripts.build_frontend
   ```
   This regenerates `frontend/`.
3. **Upload `frontend/*`** into `~/public_html/class_management/` on the
   shared host.
4. **Edit `config.js`** on the host:
   ```js
   window.API_BASE = "https://api.your-domain.example";
   window.API_TOKEN = "<same string as API_BEARER_TOKEN above>";
   ```
5. Visit `https://your-domain.example/class_management/`.

The bearer token is mandatory here — without it, the API URL in the JS
makes every write endpoint publicly callable.

---

## Repo layout

```
app/                 FastAPI app (routers, models, db helpers, services)
static/              JS + CSS source (served at /static/ in integrated mode)
templates/           HTML source (served at / in integrated mode)
frontend/            Generated static bundle for split-deploy (upload to public_html)
scripts/             ETL + build_frontend.py
tests/               pytest suite
data/                DuckDB file (gitignored)
secrets/             Service-account JSON (gitignored)
deploy/              systemd unit + Caddyfile for VPS deploy
passenger_wsgi.py    Entry point for cPanel "Setup Python App" (Passenger)
docs/                USAGE, DEPLOY (VPS), DEPLOY_CPANEL, DEPLOY_SPLIT
```

## Reference

- **API endpoints, request/response shapes, DB schema, troubleshooting:**
  [`docs/USAGE.md`](docs/USAGE.md).
- **VPS deployment (Ubuntu + Caddy + systemd):**
  [`docs/DEPLOY.md`](docs/DEPLOY.md).
- **Shared-hosting deployment (cPanel + Passenger):**
  [`docs/DEPLOY_CPANEL.md`](docs/DEPLOY_CPANEL.md).
- **Split deployment (static frontend on Apache + backend elsewhere):**
  [`docs/DEPLOY_SPLIT.md`](docs/DEPLOY_SPLIT.md).
