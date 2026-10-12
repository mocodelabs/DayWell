from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("insights/weekly-reviews", views.WeeklyReviewViewSet, basename="weekly-review")
router.register("goals", views.GoalViewSet, basename="goal")

urlpatterns = [
    path("insights/summary/", views.SummaryView.as_view()),
    path("insights/daily/", views.DailyView.as_view()),
    path("insights/weekly/", views.WeeklyView.as_view()),
    path("insights/monthly/", views.MonthlyView.as_view()),
    path("insights/yearly/", views.YearlyView.as_view()),
    *router.urls,
]
