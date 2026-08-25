"""
Django settings for config project.

Environment-driven (12-factor) configuration:

- Secrets live in environment variables / a local ``backend/.env`` file
  (see ``.env.example``). Nothing secret is hardcoded here.
- The database is Supabase Postgres, configured via ``DATABASE_URL``
  (transaction-mode pooler, port 6543). Migrations must run against the
  direct connection instead — use ``config.settings_migration`` which reads
  ``MIGRATION_DATABASE_URL`` (see docs/supabase-setup.md).
- API authentication is Supabase Auth JWTs verified by
  ``config.authentication.SupabaseJWTAuthentication``. Django's session
  auth is only used by the /admin/ site (staff accounts in accounts.User).
"""

import os
from pathlib import Path

import dj_database_url
import environ

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# DEBUG の既定は False。環境変数を付け忘れたときにデバッグページが出る側へ
# 倒れてはいけない。実際に Vercel のプレビュー環境で DJANGO_DEBUG を設定し
# 忘れており、設定値・トレースバック・Cookie を含む Django のデバッグページが
# そのまま配信されていた。ローカル開発は .env か環境変数で明示的に
# DJANGO_DEBUG=true を指定する（backend/.env.example を参照）。
env = environ.Env(DJANGO_DEBUG=(bool, False))
# Optional local env file; real deployments should use actual env vars.
environ.Env.read_env(BASE_DIR / ".env")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env("DJANGO_DEBUG")

# The previously committed SECRET_KEY is treated as leaked and must not be
# reused. Generate one with:
#   python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
SECRET_KEY = env("DJANGO_SECRET_KEY", default="")
if not SECRET_KEY:
    if DEBUG:
        # Dev-only fallback so `manage.py` works out of the box. The API is
        # stateless (JWT), so this only affects local /admin/ sessions.
        SECRET_KEY = "django-insecure-dev-only-set-DJANGO_SECRET_KEY-in-env"
    else:
        raise environ.ImproperlyConfigured(
            "DJANGO_SECRET_KEY environment variable is required when DJANGO_DEBUG=false"
        )

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'accounts',
    'quiz',
    'exams',
    'battle',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# accounts.User is kept ONLY for the Django admin (staff logins). API
# clients are represented by accounts.Profile rows keyed by the Supabase
# auth.users UUID; every app-level FK points at Profile, not User.
AUTH_USER_MODEL = 'accounts.User'

CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=['http://localhost:5173', 'http://127.0.0.1:5173'],
)

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'config.authentication.SupabaseJWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_THROTTLE_RATES': {
        # spec 6.セキュリティ: rate limits for write endpoints
        'submit-answer': '60/min',
        'question-create': '20/day',
        'question-report': '20/day',
    } if 'PYTEST_VERSION' not in os.environ else {
        # Tests hammer these endpoints; rate limiting has its own dedicated test.
        'submit-answer': '10000/min',
        'question-create': '10000/day',
        'question-report': '10000/day',
    },
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
}

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# Supabase Postgres via the transaction-mode pooler (port 6543).
# conn_max_age must stay 0 with the transaction pooler (no persistent
# server-side session; prepared statements are unsupported there, which is
# also why migrations go through config.settings_migration / port 5432).
DATABASES = {
    "default": dj_database_url.parse(
        env(
            "DATABASE_URL",
            # Local-dev default: a plain local Postgres. SQLite is no longer
            # supported (Postgres-only SQL is used: DISTINCT ON, pg_trgm).
            default="postgres://postgres:postgres@127.0.0.1:5432/medical_game",
        ),
        conn_max_age=0,
    )
}

# Supabase project wiring (see docs/supabase-setup.md).
SUPABASE_URL = env("SUPABASE_URL", default="")
SUPABASE_ANON_KEY = env("SUPABASE_ANON_KEY", default="")
# Service role key: backend only. NEVER expose to the frontend bundle.
SUPABASE_SERVICE_ROLE_KEY = env("SUPABASE_SERVICE_ROLE_KEY", default="")
# Legacy HS256 JWT secret (Dashboard > Project Settings > API > JWT Secret).
# Optional once the project uses asymmetric signing keys (below).
SUPABASE_JWT_SECRET = env("SUPABASE_JWT_SECRET", default="")
# Asymmetric verification (recommended): the project's JWKS endpoint, whose
# public keys verify RS256/ES256 tokens. Defaults to the standard Supabase
# path derived from SUPABASE_URL; override with SUPABASE_JWKS_URL if needed.
SUPABASE_JWKS_URL = env(
    "SUPABASE_JWKS_URL",
    default=(
        f"{SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"
        if SUPABASE_URL
        else ""
    ),
)
SUPABASE_JWT_AUDIENCE = "authenticated"

# Shared secret protecting /api/internal/* endpoints (called by the
# Supabase Edge Function scheduled with pg_cron; spec 4.フェーズ3).
INTERNAL_API_TOKEN = env("INTERNAL_API_TOKEN", default="")

# ランキングスナップショットの鮮度 (exams/ranking_refresh.py)。この秒数より
# 古ければ、ランキング/ホームを開いた時にその場で再集計する。外部スケジューラ
# で aggregate_rankings を回す運用にするなら負値にして遅延再集計を止める。
RANKING_SNAPSHOT_TTL_SECONDS = env.int("RANKING_SNAPSHOT_TTL_SECONDS", default=300)

# Web Push (VAPID) keys for review reminders (spec 4.フェーズ6).
VAPID_PRIVATE_KEY = env("VAPID_PRIVATE_KEY", default="")
VAPID_PUBLIC_KEY = env("VAPID_PUBLIC_KEY", default="")
VAPID_ADMIN_EMAIL = env("VAPID_ADMIN_EMAIL", default="")

# Supabase Storage bucket holding student-ID images (private).
STUDENT_ID_BUCKET = env("STUDENT_ID_BUCKET", default="student-ids")
# Retention: approved verification images are deleted after this many days
# (rejected ones are deleted immediately on rejection).
STUDENT_ID_RETENTION_DAYS = 90

# 医師国家試験の実施日（YYYY-MM-DD）。年が変わったら手動更新する運用値
# （spec: 大型模試は国試の2ヶ月前に自動開催）。デフォルトは次回の目安。
NATIONAL_EXAM_DATE = env("NATIONAL_EXAM_DATE", default="2027-02-06")


# Password validation (admin staff accounts only)
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Asia/Tokyo'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = 'static/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
