from pathlib import Path

from django.conf import settings
from django.contrib import admin
from django.http import FileResponse, Http404
from django.urls import include, path, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.core import health, scheduler

API_APPS = ["accounts", "preferences", "tasks", "events", "reminders", "habits", "affirmations", "reading", "fitness", "wellness", "insights", "briefing", "billing"]

api_v1 = [path("", include(f"apps.{name}.urls")) for name in API_APPS if Path(settings.BASE_DIR, "apps", name, "urls.py").exists()]

urlpatterns = [
    path("health/live/", health.live),
    path("health/ready/", health.ready),
    path("health/scheduler/", health.scheduler),
    path("internal/tick/", scheduler.tick),
    path("internal/email-check/", scheduler.email_check),
    path("api/v1/", include(api_v1)),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema")),
    path("django-admin/", admin.site.urls),
]


if settings.FRONTEND_DIST:
    # Single-origin deployment: Django also serves the built SPA (index.html for client-side routes).
    dist = Path(settings.FRONTEND_DIST).resolve()

    def spa(request, resource: str = ""):
        target = (dist / resource).resolve()
        if resource and target.is_file() and dist in target.parents:
            response = FileResponse(open(target, "rb"))
            if resource in ("sw.js", "manifest.webmanifest"):
                response["Cache-Control"] = "no-cache"
            elif resource.startswith("assets/"):
                response["Cache-Control"] = "public, max-age=31536000, immutable"
            return response
        index = dist / "index.html"
        if not index.exists():
            raise Http404("Frontend build not found")
        response = FileResponse(open(index, "rb"), content_type="text/html")
        response["Cache-Control"] = "no-cache"
        return response

    urlpatterns += [re_path(r"^(?P<resource>(?!api/|health/|django-admin/|static/).*)$", spa)]
