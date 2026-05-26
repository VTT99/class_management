# Deploying on the SRCF (Cambridge Student-Run Computing Facility)

End state: the UI and API both live at
`https://<crsid>.user.srcf.net/class_management/`, served by your own
uvicorn process and managed by **systemd --user** with the
`.htaccess` reverse-proxy SRCF documents.

Based on SRCF's own [deploy-a-web-app
tutorial](https://docs.srcf.net/tutorials/websites/deploy-a-web-app/)
and [web-applications
reference](https://docs.srcf.net/reference/web-hosting/web-applications/).

## Why this is different from a regular shared host

SRCF's hosting policy has two specific constraints that shape the whole
setup:

1. **Apache reverse-proxies to a Unix socket, not a TCP port.** That's
   why `RewriteRule [P]` to `http://127.0.0.1:8000/...` returns a 503
   — SRCF refuses TCP localhost proxies. Use `unix:` paths instead.
2. **Long-running processes are managed by `systemctl --user`**, not
   by `nohup` or system-wide systemd. With `loginctl enable-linger`
   your services keep running after logout.

Everything else (app code, .env, the FastAPI app itself) is the same
as the other deploys.

## Architecture

```
Browser
   │
   │ https://<crsid>.user.srcf.net/class_management/*
   ▼
+----------------------+   .htaccess  +-------------------------+
| SRCF Apache          |  ─────────►  | unix:/home/<crsid>/     |
| public_html/         |  RewriteRule |   class_management/     |
|   class_management/  |     [P]      |   web.sock              |
|     .htaccess        |              +-------------------------+
+----------------------+                           ▲
                                                   │
                                +-----------------------------------+
                                | systemd --user                    |
                                |   class-management.service        |
                                |     ExecStart=run.sh              |
                                |     uvicorn --uds web.sock        |
                                +-----------------------------------+
```

The app serves both the UI **and** the API — `SERVE_FRONTEND=true`,
`ROOT_PATH=/class_management` — because SRCF's documented `.htaccess`
proxies *every* path. Static files don't need to live in `public_html`;
FastAPI returns them via the proxied request.

## Step-by-step

### 1. SSH in and clone

```bash
ssh <crsid>@<crsid>.user.srcf.net
cd ~
git clone https://github.com/VTT99/class_management.git
cd ~/class_management
```

### 2. Create the venv

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install --prefer-binary -r requirements.txt
```

The `--prefer-binary` flag avoids a multi-hour duckdb compile on
SRCF's Python 3.8 (which we already accounted for in `requirements.txt`).

### 3. Configure `.env`

```bash
cp .env.example .env
nano .env
```

Set:

```
DUCKDB_FILE=data/tutorial_center.duckdb
GOOGLE_SERVICE_ACCOUNT_FILE=secrets/service_account.json
GOOGLE_CALENDAR_ID=...your calendar...
GOOGLE_SHEETS_SPREADSHEET_ID=...your sheet...
TIMEZONE=Europe/London
LOG_LEVEL=INFO

# Critical for SRCF: the app must serve everything (UI + API) because
# the .htaccess proxies every path.
SERVE_FRONTEND=true
ROOT_PATH=/class_management

# Recommended even on SRCF since the site is public:
API_BEARER_TOKEN=<long-random-string>

# Optional: override the default socket path.
# SRCF_UVICORN_SOCKET=/home/<crsid>/class_management/web.sock
```

### 4. Drop the service-account JSON and DuckDB

```bash
# secrets/service_account.json
mkdir -p secrets
# scp from your laptop into secrets/, then:
chmod 700 secrets
chmod 600 secrets/service_account.json

# data/tutorial_center.duckdb (either scp it, or regenerate):
mkdir -p data
.venv/bin/python -m scripts.download_sheet_to_db
```

### 5. Stop any old uvicorn (from a previous deploy attempt)

```bash
./deploy/stop.sh 2>/dev/null || true
```

### 6. Install the systemd user service

```bash
mkdir -p ~/.config/systemd/user
cp ~/class_management/deploy/srcf/class-management.service ~/.config/systemd/user/

# Tell systemd to keep your services running after you log out.
# You only need to do this once per SRCF account.
loginctl enable-linger $USER

systemctl --user daemon-reload
systemctl --user enable --now class-management
systemctl --user status class-management --no-pager
```

The status output should show `active (running)` and a pid. If it
errors, check the journal:

```bash
journalctl --user -u class-management -n 50 --no-pager
```

Quick check from the host that uvicorn is up and listening on the
socket:

```bash
curl --unix-socket ~/class_management/web.sock http://localhost/health
# {"status":"ok","db":"ok","calendar_configured":true}
```

### 7. Install the SRCF `.htaccess`

```bash
mkdir -p ~/public_html/class_management

# Copy the template
cp ~/class_management/deploy/srcf/htaccess-srcf.example \
   ~/public_html/class_management/.htaccess

# Edit the placeholder <YOUR-CRSID> to your actual CRSid
nano ~/public_html/class_management/.htaccess
```

The line you edit looks like:

```
RewriteRule ^(.*)$ unix:/home/<YOUR-CRSID>/class_management/web.sock|http://localhost/$1 [P,NE,L,QSA]
```

For CRSid `twt27`:

```
RewriteRule ^(.*)$ unix:/home/twt27/class_management/web.sock|http://localhost/$1 [P,NE,L,QSA]
```

### 8. (Important) clean up the old split-deploy files

If you previously copied `frontend/*` into `public_html/class_management/`
during the earlier attempt, those files become unreachable in this
layout (everything goes via the proxy). They're harmless but make
debugging confusing. Optional cleanup:

```bash
cd ~/public_html/class_management
ls -la                                  # see what's there
# Keep only .htaccess. Delete the rest:
find . -maxdepth 1 ! -name . ! -name .htaccess -exec rm -rf {} +
ls -la                                  # should now show only .htaccess
```

### 9. Verify

From your laptop:

```bash
curl -i https://<crsid>.user.srcf.net/class_management/health
# HTTP/1.1 200 OK
# {"status":"ok","db":"ok","calendar_configured":true}
```

Then in a browser, open `https://<crsid>.user.srcf.net/class_management/`.
The UI loads, the health badge in the corner turns green, and entering
a student ID returns data.

## Day-to-day

```bash
# Status
systemctl --user status class-management

# Tail logs
journalctl --user -u class-management -f

# Restart after a code or .env change
systemctl --user restart class-management

# Stop / start
systemctl --user stop class-management
systemctl --user start class-management

# Pull updates from GitHub
cd ~/class_management
git pull
.venv/bin/pip install -r requirements.txt   # if requirements changed
systemctl --user restart class-management
```

## Troubleshooting

- **`curl https://.../class_management/health` returns 503** —
  uvicorn isn't running or the socket path in `.htaccess` is wrong.
  Check both:
  ```bash
  systemctl --user status class-management
  ls -l ~/class_management/web.sock
  ```
  The socket file must exist; if not, the service didn't start
  (`journalctl --user -u class-management -n 50`).
- **`curl ... /class_management/health` returns 404 (SRCF default
  page)** — the `.htaccess` isn't in
  `~/public_html/class_management/`, or it's named `htaccess` without
  the leading dot. `ls -la ~/public_html/class_management/`.
- **`curl ... /class_management/health` returns 500** — the
  `RewriteRule` syntax is wrong. Make sure you edited
  `<YOUR-CRSID>` to your actual CRSid, the socket path is right, and
  there are no stray characters.
- **HTML loads but assets 404** — the path the `<link>`/`<script>`
  tags use doesn't match `ROOT_PATH`. Confirm `.env` has
  `ROOT_PATH=/class_management` and that `systemctl --user restart
  class-management` was run after the edit.
- **Service dies after logout** — you skipped `loginctl enable-linger
  $USER`. Run it (only needs doing once).
- **Calendar 503 "not configured"** — `.env` is missing
  `GOOGLE_CALENDAR_ID` or `secrets/service_account.json` isn't
  present/readable.
- **Service won't start, journal shows
  `ModuleNotFoundError: No module named 'app'`** — the
  `WorkingDirectory` isn't set; double-check `cat
  ~/.config/systemd/user/class-management.service` matches the file
  in `deploy/srcf/`.

## Why no `nohup`, no `.htaccess` to TCP port?

Both fail on SRCF:

- `nohup`'d processes get cleaned up when SRCF's session-keeper notices
  no active login. `loginctl enable-linger` + `systemctl --user` is the
  documented way to keep services running.
- TCP localhost proxying via `RewriteRule … [P]` is denied by SRCF's
  Apache config, which is why our first attempt got `HTTP/1.1 503
  Service Unavailable`. The Unix-socket form is the one they allow.

## Comparison with the other shared-host deploy

If you ever move to a different shared host, here's what the same
piece of work would look like there:

|                        | SRCF                                              | Generic shared host (DEPLOY_SAME_HOST.md) |
| ---------------------- | ------------------------------------------------- | ----------------------------------------- |
| Server binds to        | Unix socket                                       | TCP localhost                             |
| Supervision            | systemctl --user (+ linger)                       | nohup                                     |
| .htaccess proxy target | `unix:/path/web.sock`                             | `http://127.0.0.1:8000`                   |
| Header passthrough     | `RequestHeader set` directives                    | Not required                              |
| Static files location  | None — app serves everything                       | public_html (proxy only catches /api/*)   |
| `SERVE_FRONTEND`       | `true`                                            | `false`                                    |
| `ROOT_PATH`            | `/class_management`                               | `/class_management/api`                   |
