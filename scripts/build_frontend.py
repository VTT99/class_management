"""Build the static frontend bundle for split deployment.

Reads templates/index.html + static/, strips the Jinja substitutions and
the data-root-path indirection, inserts a `<script src="config.js">`
include, and writes everything to frontend/. The output is what you
upload to your Apache `public_html` directory.

Run with:
    python -m scripts.build_frontend
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from app.config import REPO_ROOT

SRC_HTML = REPO_ROOT / "templates" / "index.html"
SRC_STATIC = REPO_ROOT / "static"
DEST = REPO_ROOT / "frontend"
DEST_STATIC = DEST / "static"


CONFIG_JS = """\
// Edit these two lines after uploading, then reload the page.
// API_BASE: full URL of the FastAPI backend (no trailing slash).
// API_TOKEN: must match API_BEARER_TOKEN on the backend (or "" to disable).
window.API_BASE = "https://api.your-domain.example";
window.API_TOKEN = "";
"""


FRONTEND_README = """\
# Static frontend bundle

This directory is what you upload to your Apache `public_html` to serve the
Tutorial Center UI on shared hosting. It talks to a FastAPI backend running
somewhere else (your own VPS / Fly.io / Render / etc).

## Upload

1. Copy the entire contents of this directory into a folder on your host,
   e.g. `~/public_html/class_management/`.
2. Edit `config.js`:
   ```js
   window.API_BASE = "https://api.your-domain.example";   // your backend
   window.API_TOKEN = "the-same-secret-as-API_BEARER_TOKEN-on-backend";
   ```
3. On the backend, make sure your `.env` has:
   ```
   SERVE_FRONTEND=false
   ALLOWED_ORIGINS=https://your-domain.example
   API_BEARER_TOKEN=the-same-secret-as-in-config.js
   ROOT_PATH=
   ```
   (`ALLOWED_ORIGINS` must match the origin from which the browser loads
   this frontend, e.g. `https://example.edu`. Add multiple origins
   comma-separated if needed.)

4. Restart the backend so it picks up the new `.env`.
5. Open `https://your-domain.example/class_management/` in a browser.

## Regenerating

This bundle is generated from `templates/index.html` and `static/` by
`scripts/build_frontend.py`. If you change the HTML/CSS/JS in those
locations, regenerate the bundle:

```
python -m scripts.build_frontend
```

## See also

- `../docs/DEPLOY_SPLIT.md` — full walkthrough of the split deployment.
"""


def build() -> None:
    if DEST.exists():
        shutil.rmtree(DEST)
    DEST.mkdir(parents=True)

    # Copy static/ unchanged. app.js already supports window.API_BASE /
    # window.API_TOKEN and falls back to the integrated-mode behaviour, so
    # one file works for both deploys.
    shutil.copytree(SRC_STATIC, DEST_STATIC)

    # Rewrite the HTML: strip Jinja substitutions (no server-side render
    # available on Apache), make asset URLs relative, and prepend a
    # <script src="config.js"> include.
    html = SRC_HTML.read_text(encoding="utf-8")
    html = html.replace(
        '<link rel="stylesheet" href="{{ root_path }}/static/css/style.css">',
        '<link rel="stylesheet" href="static/css/style.css">',
    )
    html = html.replace(
        '<script src="{{ root_path }}/static/js/app.js" data-root-path="{{ root_path }}" defer></script>',
        '<script src="config.js"></script>\n    <script src="static/js/app.js" defer></script>',
    )

    if "{{ root_path }}" in html:
        print("WARNING: leftover {{ root_path }} markers in index.html — update the build script.")

    (DEST / "index.html").write_text(html, encoding="utf-8")
    (DEST / "config.js").write_text(CONFIG_JS, encoding="utf-8")
    (DEST / "README.md").write_text(FRONTEND_README, encoding="utf-8")

    print(f"Wrote {DEST.relative_to(REPO_ROOT)}/ — upload its contents to your public_html.")


if __name__ == "__main__":
    build()
    sys.exit(0)
