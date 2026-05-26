# Split deployment: static frontend on Apache + FastAPI backend elsewhere

Use this when your shared host can only serve static files from
`public_html`, and the FastAPI process needs to live on a different machine
(your own VPS, Fly.io, Render, your laptop, …).

## Architecture

```
Browser
   │
   │ 1. GET https://your-domain.example/class_management/  (static)
   ▼
+--------+      +-----------------------+
| Apache |  ←   | ~/public_html/        |
|        |      |   class_management/   |
|        |      |     index.html        |
|        |      |     config.js   ← edit this once
|        |      |     static/{css,js}   |
+--------+      +-----------------------+

   │ 2. Browser runs JS, reads window.API_BASE + window.API_TOKEN
   │ 3. fetch("https://api.your-domain.example/student_data", { Authorization: Bearer ... })
   ▼
+--------------------+       +---------------------+
| api.your-domain    |  →    | uvicorn FastAPI     |
| (DNS A record)     |       | SERVE_FRONTEND=false|
+--------------------+       | CORS allows the     |
                             | static origin       |
                             +---------------------+
```

Two origins:

- **Frontend origin**, e.g. `https://your-domain.example` — Apache serves
  the static files from `public_html`.
- **Backend origin**, e.g. `https://api.your-domain.example` — uvicorn
  (under systemd + Caddy, or a free-tier PaaS) serves the JSON API.

CORS allows the frontend origin to call the backend. A shared bearer
token authenticates writes.

## 1. Run the backend somewhere

You need a host that can run a Python long-running process. Anywhere
from a $5 VPS to a free tier:

- **Your own Ubuntu VPS** — follow [`DEPLOY.md`](DEPLOY.md). Skip the
  Caddy `handle_path` sub-path and use a clean domain like
  `api.your-domain.example`.
- **Fly.io / Render / Railway** — wrap the same `app.main:app` in their
  Python service config. They expose HTTPS automatically.
- **Your laptop, briefly, for testing** — `uvicorn app.main:app --port
  8000` plus a tunnel (`ngrok http 8000`, `tailscale serve`).

Whichever you pick, the backend's `.env` must include:

```
SERVE_FRONTEND=false
ALLOWED_ORIGINS=https://your-domain.example      # the static origin(s), comma-separated
API_BEARER_TOKEN=some-long-random-string         # required — see below
ROOT_PATH=                                       # empty; API is at "/"
GOOGLE_CALENDAR_ID=...
GOOGLE_SHEETS_SPREADSHEET_ID=...
```

- `SERVE_FRONTEND=false` makes the backend skip mounting `/static` and
  registering the `/` HTML route. The API endpoints stay unchanged.
- `ALLOWED_ORIGINS` is the browser-visible origin that loads the static
  HTML. **The protocol must match** — `https://your-domain.example`, not
  `http://your-domain.example`.
- **`API_BEARER_TOKEN` is mandatory in this layout.** Because the JS
  contains the API URL, anyone can otherwise call the write endpoints.
  Pick a long random string (`openssl rand -base64 32`), put it in both
  the backend `.env` and the frontend `config.js`.

## 2. Build the static bundle

On your laptop:

```bash
cd ~/class_management
python -m scripts.build_frontend
```

This (re)generates `frontend/`:

```
frontend/
├── index.html
├── config.js            ← you edit this after upload
├── README.md
└── static/
    ├── css/style.css
    └── js/app.js
```

## 3. Upload to the shared host

Two options:

**A. SFTP from your laptop.** Drag the *contents* of `frontend/` into
`~/public_html/class_management/`.

**B. Clone the repo on the host and copy.** If you have SSH:

```bash
cd ~
git clone https://github.com/VTT99/class_management.git
mkdir -p ~/public_html/class_management
cp -r ~/class_management/frontend/* ~/public_html/class_management/
```

(`~/class_management/` itself stays outside `public_html` since you only
need the bundle there.)

## 4. Edit `config.js`

In `~/public_html/class_management/config.js`:

```js
window.API_BASE = "https://api.your-domain.example";
window.API_TOKEN = "the-same-string-as-API_BEARER_TOKEN-on-backend";
```

No quotes wrong, no trailing slash on `API_BASE`.

## 5. Verify

In a browser, open:

```
https://your-domain.example/class_management/
```

Open the DevTools network tab and click around the UI. You should see:

- `GET https://your-domain.example/class_management/static/css/style.css` → 200
- `GET https://api.your-domain.example/health` → 200, `Authorization: Bearer ...`
- The health badge in the corner turning green.

If the badge stays red:

- **CORS error in console** ("blocked by CORS policy") → `ALLOWED_ORIGINS`
  on the backend doesn't match exactly. Check protocol + host + port.
- **401 Unauthorized** → `window.API_TOKEN` in `config.js` doesn't match
  `API_BEARER_TOKEN` in the backend `.env`.
- **Mixed-content warning** → frontend is HTTPS but `API_BASE` is HTTP.
  Browsers block this; the backend must be on HTTPS too.

## Updating

**Frontend:** rebuild + re-upload.

```bash
cd ~/class_management && git pull
python -m scripts.build_frontend
# scp / sftp frontend/* to ~/public_html/class_management/  on the shared host
# (don't overwrite config.js — keep the edited copy)
```

**Backend:** restart the backend process per whichever deploy you chose
(`sudo systemctl restart class-management` on a VPS, `fly deploy` on
Fly.io, etc.).

## Trade-offs vs the integrated layouts

|                                 | Integrated (VPS / cPanel) | Split             |
|---------------------------------|---------------------------|-------------------|
| One deploy or two?              | One                       | Two               |
| Static cache hit when API down? | No (Python serves HTML)   | Yes (Apache only) |
| API URL visible to users?       | No (same origin)          | Yes (in JS)       |
| Auth required?                  | Optional                  | **Mandatory**     |
| Cross-origin CORS complexity?   | None                      | Real              |
| Where to host the backend?      | One machine               | Free-tier PaaS / your own VPS / anywhere |

Use the split layout when you have to (your shared host can't run
Python). The integrated layout is simpler if you have the choice.
