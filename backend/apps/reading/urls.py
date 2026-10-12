from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("reading/books", views.BookViewSet, basename="book")
router.register("reading/sessions", views.SessionViewSet, basename="reading-session")

urlpatterns = [
    path("reading/stats/", views.ReadingStatsView.as_view()),
    path("reading/reminder/", views.ReadingReminderView.as_view()),
    *router.urls,
]
