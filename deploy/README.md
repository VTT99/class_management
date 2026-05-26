# Deploy artifacts

- `class-management.service` — systemd unit to run uvicorn under a dedicated
  user.
- `Caddyfile` — minimal reverse-proxy config that maps
  `https://your-domain/class_management/*` to the local uvicorn process.

See `../docs/DEPLOY.md` for the full step-by-step.
