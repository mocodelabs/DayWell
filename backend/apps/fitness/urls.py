from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("fitness/routines", views.RoutineViewSet, basename="routine")
router.register("fitness/sessions", views.SessionViewSet, basename="workout-session")

urlpatterns = [path("fitness/stats/", views.FitnessStatsView.as_view()), *router.urls]
