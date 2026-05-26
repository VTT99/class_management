# Deploying to an Ubuntu VPS under `https://test.com/class_management`

Target: a fresh Ubuntu 22.04 / 24.04 server with a public IP, SSH access, and
your domain (e.g. `test.com`) pointing at it via an A/AAAA record. Caddy
handles HTTPS automatically.

Reverse-proxy: **Caddy**. Process manager: **systemd**. Python: 3.11+.

> Throughout this guide, replace `test.com` with your real domain.

## 1. DNS

Create an A record for the hostname you'll use, pointing at the server's
public IP:

```
test.com         A   203.0.113.45
www.test.com     A   203.0.113.45    # optional
```

Confirm with `dig +short test.com` from your laptop.

## 2. Open firewall ports

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

## 3. Create a service user

```bash
sudo adduser --system --group --home /opt/class_management --shell /usr/sbin/nologin class-management
```

## 4. Install Python & build deps

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
```

## 5. Pull the code

```bash
sudo -u class-management git clone https://github.com/VTT99/class_management.git /opt/class_management
cd /opt/class_management
sudo -u class-management python3 -m venv .venv
sudo -u class-management .venv/bin/pip install -r requirements.txt
```

## 6. Configure `.env`

```bash
sudo -u class-management cp .env.example .env
sudo -u class-management $EDITOR .env
```

Set at minimum:

```
DUCKDB_FILE=data/tutorial_center.duckdb
GOOGLE_SERVICE_ACCOUNT_FILE=secrets/service_account.json
GOOGLE_CALENDAR_ID=...your calendar...
GOOGLE_SHEETS_SPREADSHEET_ID=...your sheet...
TIMEZONE=Asia/Hong_Kong
LOG_LEVEL=INFO

# IMPORTANT: matches the sub-path Caddy forwards.
ROOT_PATH=/class_management

# Optional: protect the API with a bearer token.
# API_BEARER_TOKEN=some-long-random-string
```

## 7. Drop the service-account JSON

```bash
sudo install -d -o class-management -g class-management -m 750 /opt/class_management/secrets
# Scp the file from your laptop, then:
sudo install -o class-management -g class-management -m 600 service_account.json /opt/class_management/secrets/service_account.json
```

## 8. Populate the DuckDB

Either copy an existing file:

```bash
sudo install -d -o class-management -g class-management -m 750 /opt/class_management/data
sudo install -o class-management -g class-management -m 640 tutorial_center.duckdb /opt/class_management/data/
```

Or hydrate from Google Sheets:

```bash
sudo -u class-management /opt/class_management/.venv/bin/python -m scripts.download_sheet_to_db
```

## 9. Install the systemd unit

```bash
sudo cp /opt/class_management/deploy/class-management.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now class-management
sudo systemctl status class-management --no-pager
```

Smoke check from the server itself:

```bash
curl -s http://127.0.0.1:8000/health
# {"status":"ok","db":"ok","calendar_configured":true}
```

## 10. Install and configure Caddy

```bash
# Caddy's official APT repo
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install -y caddy
```

Replace `/etc/caddy/Caddyfile` with the snippet from
`/opt/class_management/deploy/Caddyfile` (edit the hostname first):

```bash
sudo install -o root -g root -m 644 /opt/class_management/deploy/Caddyfile /etc/caddy/Caddyfile
sudo $EDITOR /etc/caddy/Caddyfile     # change test.com -> your real domain
sudo systemctl reload caddy
sudo systemctl status caddy --no-pager
```

Caddy will request a Let's Encrypt certificate on first start. You can watch
the log with `sudo journalctl -u caddy -f`.

## 11. Verify end-to-end

From your laptop:

```bash
curl -i https://test.com/class_management/health
# HTTP/2 200
# {"status":"ok",...}
```

Then open `https://test.com/class_management/` in a browser — the UI should
load, the health badge should turn green, and you should be able to fetch
student data.

## Updating the deployment

```bash
sudo -u class-management git -C /opt/class_management pull
sudo -u class-management /opt/class_management/.venv/bin/pip install -r /opt/class_management/requirements.txt
sudo systemctl restart class-management
```

## Backups

The DuckDB file lives at `/opt/class_management/data/tutorial_center.duckdb`.
A nightly cron is enough:

```cron
0 3 * * *  cp /opt/class_management/data/tutorial_center.duckdb /var/backups/tutorial_center_$(date +\%F).duckdb
```

## Troubleshooting

- **502/504 from Caddy** — the systemd unit isn't running, or it's listening
  on the wrong port. `sudo journalctl -u class-management -n 50`.
- **404 on `/class_management/static/...`** — `ROOT_PATH` in `.env` does not
  match the Caddy `handle_path` prefix.
- **`certificate not yet trusted`** — DNS hasn't propagated yet, or the
  domain points elsewhere. Wait a few minutes; re-check `dig +short`.
- **`Permission denied` on data file** — the service user
  (`class-management`) needs ownership of `/opt/class_management/data`
  (read+write) and `secrets` (read).
- **Calendar 503 "not configured"** — `GOOGLE_CALENDAR_ID` empty or the
  service-account file is missing on the server.

## Security notes

- `API_BEARER_TOKEN` is empty by default. If the URL is public, set it to a
  long random string so writes (`/add_student`, `/mark_attendance`,
  calendar endpoints) require `Authorization: Bearer <token>`.
- The service runs as a non-login system user with `ProtectSystem=strict`
  and `ProtectHome=true`; only `/opt/class_management/data` is writable.
- Caddy listens on 80/443 only; uvicorn binds to `127.0.0.1:8000`, never
  exposed directly to the internet.
- Do not commit `.env`, `secrets/`, or `data/` — they're already in
  `.gitignore`.
