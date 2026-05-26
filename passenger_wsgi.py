"""Phusion Passenger entry point for cPanel "Setup Python App".

cPanel + Passenger speak WSGI. Our app is ASGI (FastAPI/Starlette).
We wrap it with a2wsgi so Passenger can call into it.

cPanel mounts the app under a sub-URI by passing `SCRIPT_NAME` in the WSGI
environ; a2wsgi propagates that to the ASGI scope's `root_path`, so the
backend automatically knows it lives under e.g. `/class_management`.

In cPanel's "Setup Python App" UI:
    Application startup file = passenger_wsgi.py
    Application entry point  = application
"""

import os
import sys

# Make sure the project root is on sys.path so `import app.main` works no
# matter where Passenger boots us from.
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from a2wsgi import ASGIMiddleware  # noqa: E402
from app.main import app as _asgi_app  # noqa: E402

application = ASGIMiddleware(_asgi_app)
