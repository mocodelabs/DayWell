from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("wellness/water", views.HydrationViewSet, basename="water")
router.register("wellness/sleep", views.SleepViewSet, basename="sleep")
router.register("wellness/journal", views.JournalViewSet, basename="journal")
router.register("wellness/mindfulness", views.MindfulnessViewSet, basename="mindfulness")

urlpatterns = [
    path("wellness/water-reminder/", views.HydrationReminderView.as_view()),
    path("wellness/sleep-reminder/<str:kind>/", views.SleepReminderView.as_view()),
    *router.urls,
]
