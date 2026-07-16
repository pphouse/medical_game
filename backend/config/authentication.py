from rest_framework.authentication import SessionAuthentication


class CsrfExemptSessionAuthentication(SessionAuthentication):
    """Local-demo only: skips CSRF enforcement so the Vite dev-server
    frontend can call session-authenticated endpoints without wiring up
    CSRF token exchange. Do not use this as-is in production.
    """

    def enforce_csrf(self, request):
        return
