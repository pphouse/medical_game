"""Settings module for running migrations against Supabase.

The transaction-mode pooler (port 6543) does not support prepared
statements, so ``manage.py migrate`` must use the direct connection
(port 5432) instead:

    python manage.py migrate --settings=config.settings_migration

Reads ``MIGRATION_DATABASE_URL``; falls back to ``DATABASE_URL`` so local
development (where both point at the same plain Postgres) keeps working.
"""

import dj_database_url

from .settings import *  # noqa: F401,F403
from .settings import env

_migration_url = env("MIGRATION_DATABASE_URL", default="")
if _migration_url:
    DATABASES = {"default": dj_database_url.parse(_migration_url, conn_max_age=0)}
