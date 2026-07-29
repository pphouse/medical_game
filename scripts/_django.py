"""Bootstrap Django so standalone scripts can use the ORM.

Usage:  from _django import setup_django; setup_django()
"""

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"


def setup_django():
    sys.path.insert(0, str(BACKEND_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
