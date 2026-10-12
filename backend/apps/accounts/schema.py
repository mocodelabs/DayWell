from drf_spectacular.extensions import OpenApiAuthenticationExtension


class SessionAuthScheme(OpenApiAuthenticationExtension):
    """Documents DayWell's cookie session auth (CSRF header required on unsafe methods) in the OpenAPI schema."""

    target_class = "apps.accounts.authentication.SessionAuthentication"
    name = "sessionAuth"

    def get_security_definition(self, auto_schema):
        return {"type": "apiKey", "in": "cookie", "name": "daywell_session"}
