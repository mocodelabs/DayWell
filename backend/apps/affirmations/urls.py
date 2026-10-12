from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("affirmations/library", views.AffirmationViewSet, basename="affirmation")
router.register("affirmations/history", views.HistoryView, basename="affirmation-history")

urlpatterns = [
    path("affirmations/today/", views.TodayAffirmationView.as_view()),
    path("affirmations/daily/<int:pk>/<str:verb>/", views.DailyAffirmationActionView.as_view()),
    path("affirmations/reminder/", views.AffirmationReminderView.as_view()),
    *router.urls,
]
