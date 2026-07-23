import pytest


@pytest.fixture(autouse=True)
def _test_secrets(settings):
    """Give every test a working JWT secret / internal token so the suite
    runs without a real Supabase project (pytest-django restores the
    originals after each test)."""
    if not settings.SUPABASE_JWT_SECRET:
        settings.SUPABASE_JWT_SECRET = "test-jwt-secret-not-for-production"
    if not settings.INTERNAL_API_TOKEN:
        settings.INTERNAL_API_TOKEN = "test-internal-token"
