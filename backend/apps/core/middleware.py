import re
import uuid

from .logging import request_id_var

_VALID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


class RequestIdMiddleware:
    """Tags every request with an id (honouring a sane incoming X-Request-ID) for log correlation."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.headers.get("X-Request-ID", "")
        rid = incoming if _VALID.match(incoming) else uuid.uuid4().hex
        # Not reset afterwards on purpose: Django logs 4xx/5xx responses after the middleware chain returns, and those
        # lines should carry the id too. Every request sets its own id first, so nothing leaks between requests.
        request_id_var.set(rid)
        response = self.get_response(request)
        response["X-Request-ID"] = rid
        return response


class HealthProbeMiddleware:
    """Answer /health/* before host validation and the HTTPS redirect.

    Container and load-balancer probes call the app directly (e.g. http://127.0.0.1:8000/health/ready/), which would
    otherwise fail ALLOWED_HOSTS and be redirected to HTTPS. Health responses contain no user data.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path_info.startswith("/health/"):
            from . import health

            view = {"/health/live/": health.live, "/health/ready/": health.ready, "/health/scheduler/": health.scheduler}.get(request.path_info)
            if view is not None and request.method in ("GET", "HEAD"):
                return view(request)
        return self.get_response(request)
