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
