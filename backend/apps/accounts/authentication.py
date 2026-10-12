from rest_framework import authentication


class SessionAuthentication(authentication.SessionAuthentication):
    """DRF session auth (CSRF-enforced) that answers 401 instead of 403 when no session is present,
    so the SPA can tell "signed out" apart from "forbidden"."""

    def authenticate_header(self, request) -> str:
        return 'Session realm="api"'
