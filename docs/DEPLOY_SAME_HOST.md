# Same-host deploy: static frontend in `public_html` + backend on the same machine

Use this when:

- Your shared host serves static files from `~/public_html/` via Apache.
- You can SSH in and run a Python process (uvicorn) in the background.
- Apache has **`mod_proxy`** + **`mod_proxy_http`** + **`mod_rewrite`** so
  you can reverse-proxy from `.htaccess`.

This is the cleanest layout for educational / lab / cPanel-less shared
hosts that *can* run Python: same origin in the browser, no CORS, no
exposed API URL in JS.

## Architecture

```
Browser
   │
   │ https://your-domain/class_management/*
   ▼
+------------------+
|  Apache          |
|  ~/public_html/  |        .htaccess
|  class_management/   ┌─ matches  /api/*  →  proxy to 127.0.0.1:8000
|     index.html       │                       (mod_proxy)
|     config.js        │
|     static/...       └─ everything else: served as plain files
|     .htaccess
+------------------+
                    │
                    ▼ (only reachable from this same machine)
              +-----------------+
              | uvicorn         |
              | 127.0.0.1:8000  |
              | app.main:app    |
              +-----------------+
```

## URL scheme

| Browser URL                                            | Served by | Result                                    |
| ------------------------------------------------------ | --------- | ----------------------------------------- |
| `https://your-domain/class_management/`                | Apache    | `~/public_html/class_management/index.html` |
| `https://your-domain/class_management/static/css/...`  | Apache    | static file                               |
| `https://your-domain/class_management/api/health`      | uvicorn   | proxied to `http://127.0.0.1:8000/health` |
| `https://your-domain/class_management/api/student_data` | uvicorn  | proxied to `http://127.0.0.1:8000/student_data` |

## Step-by-step

### 1. Clone the repo into your home dir (NOT into public_html)

```bash
ssh you@your-shared-host
cd ~
git clone https://github.com/VTT99/class_management.git
cd class_management

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 2. Configure `.env`

```bash
cp .env.example .env
nano .env
```

Set:

```
DUCKDB_FILE=data/tutorial_center.duckdb
GOOGLE_SERVICE_ACCOUNT_FILE=secrets/service_account.json
GOOGLE_CALENDAR_ID=...
GOOGLE_SHEETS_SPREADSHEET_ID=...
TIMEZONE=Asia/Hong_Kong
LOG_LEVEL=INFO

# Same-host layout:
SERVE_FRONTEND=false              # Apache serves the UI
ROOT_PATH=/class_management/api   # Lets OpenAPI/Swagger build correct URLs

# Token is optional here (browser sees one origin, JS doesn't see the
# token), but recommended if you'd ever expose 127.0.0.1:8000 to the LAN.
# API_BEARER_TOKEN=

# ALLOWED_ORIGINS is unused in same-origin mode; leave it empty or default.
```

### 3. Drop the service-account JSON and DuckDB

```bash
# secrets/service_account.json
chmod 700 secrets
chmod 600 secrets/service_account.json

# data/tutorial_center.duckdb
mkdir -p data
# scp from laptop, or:
.venv/bin/python -m scripts.download_sheet_to_db
```

### 4. Start the backend in the background

```bash
./deploy/start.sh
```

The script:

- creates `.venv` if missing,
- kills any previous uvicorn it started,
- launches a fresh one with `nohup`,
- writes the pid to `.uvicorn.pid` and logs to `uvicorn.log`.

Verify it's listening:

```bash
curl -s http://127.0.0.1:8000/health
# {"status":"ok","db":"ok","calendar_configured":true}
```

To stop it later:

```bash
./deploy/stop.sh
```

### 5. Build the static frontend bundle

On your **laptop**:

```bash
python -m scripts.build_frontend
# Wrote frontend/ - upload its contents to your public_html.
```

### 6. Upload `frontend/*` into `~/public_html/class_management/`

Either drag the files in via SFTP, or on the host:

```bash
mkdir -p ~/public_html/class_management
cp -r ~/class_management/frontend/* ~/public_html/class_management/
```

### 7. Install the `.htaccess`

```bash
cp ~/class_management/deploy/htaccess-apache-proxy.example \
   ~/public_html/class_management/.htaccess
```

You don't have to edit it.

### 8. Edit `config.js` for same-origin mode

In `~/public_html/class_management/config.js`:

```js
window.API_BASE = "/class_management/api";   // relative path, same origin
window.API_TOKEN = "";                       // unset, since same-origin
```

If you did set `API_BEARER_TOKEN` in step 2, put the same value in
`API_TOKEN` here.

### 9. Verify

In a browser, open:

```
https://your-domain/class_management/
```

Open DevTools → Network. You should see:

| Request                                                   | Status | Source  |
| --------------------------------------------------------- | ------ | ------- |
| `class_management/`                                       | 200    | Apache  |
| `class_management/static/css/style.css`                   | 200    | Apache  |
| `class_management/static/js/app.js`                       | 200    | Apache  |
| `class_management/config.js`                              | 200    | Apache  |
| `class_management/api/health`                             | 200    | uvicorn |
| (other endpoints once you click around the UI)            | 200    | uvicorn |

The health badge in the corner should turn green.

## Updating

When you push new code to GitHub:

```bash
# On the host:
cd ~/class_management
git pull
.venv/bin/pip install -r requirements.txt   # if requirements changed
./deploy/start.sh                           # restarts uvicorn

# Rebuild + re-upload static side:
# On your laptop:
python -m scripts.build_frontend
scp -r frontend/* you@your-host:public_html/class_management/
# (skip overwriting .htaccess and config.js — your edits live there)
```

## Keeping uvicorn alive after a logout / server reboot

`nohup` survives SSH logout but **not** a server reboot. Two options:

### Option A: cron @reboot

```bash
crontab -e
```

Add:

```cron
@reboot cd ~/class_management && ./deploy/start.sh >/dev/null 2>&1
```

After the next reboot, uvicorn comes back automatically. Many shared
hosts allow this; some don't.

### Option B: tmux (manual but visible)

```bash
tmux new -s tutorial
./deploy/start.sh
# Press Ctrl-b then d to detach. Reattach with: tmux attach -t tutorial
```

If the host kills idle tmux sessions, fall back to option A.

## Troubleshooting

- **`502 Bad Gateway` from Apache** — uvicorn isn't running, or it's
  listening on the wrong port. `./deploy/start.sh` and check `uvicorn.log`.
- **`403 Forbidden` from `.htaccess`** — your host disallows the `[P]`
  proxy flag. Try the [split-deploy
  pattern](DEPLOY_SPLIT.md) instead: backend on its own external URL,
  frontend talks to it cross-origin with a token.
- **404 on `/class_management/api/...` but the same path works via
  `127.0.0.1:8000` directly** — `mod_proxy` / `mod_proxy_http` aren't
  enabled. Same fix: use the split deploy.
- **Calendar 503 "not configured"** — `.env` missing
  `GOOGLE_CALENDAR_ID`, or `secrets/service_account.json` isn't readable.
- **DuckDB lock error** — only one process can write at a time; make
  sure `./deploy/start.sh` killed the previous instance (it does
  automatically). `ls -la .uvicorn.pid`.
- **uvicorn dies after logout despite nohup** — the host is reaping
  user processes. Use cron @reboot, or ask the host whether they support
  long-running user processes.

## Comparison with the other deploys

|                              | Same-host (this doc) | Split deploy           |
|------------------------------|----------------------|------------------------|
| Number of machines           | 1                    | 2+                     |
| CORS                         | None (same origin)   | Required               |
| API URL in client JS         | Relative `/api`      | Full external URL      |
| Token mandatory?             | No (same origin)     | **Yes**                |
| Requires `mod_proxy`?        | **Yes**              | No                     |
| Requires `public_html` host? | Yes                  | Yes                    |
| Backend can live remotely?   | No                   | Yes                    |

Pick this layout if your single host can do both — it's simpler.
