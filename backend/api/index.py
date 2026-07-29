"""Vercel Python entry point — exposes the Django WSGI app as `app`.

Vercel's @vercel/python runtime serves the module-level `app` callable for
every request routed here (see ../vercel.json). Runtime configuration comes
entirely from environment variables set in the Vercel project (DATABASE_URL,
SUPABASE_*, DJANGO_SECRET_KEY, DJANGO_ALLOWED_HOSTS, ...).

Migrations are NOT run here — apply them out-of-band against the Supabase
direct connection (see docs/deploy-vercel.md).
"""

import os
import sys
from pathlib import Path

# Ensure the Django project root (backend/) is importable when this file runs
# from backend/api/ on Vercel.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.core.wsgi import get_wsgi_application  # noqa: E402

app = get_wsgi_application()
