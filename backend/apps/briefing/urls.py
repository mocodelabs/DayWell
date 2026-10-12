from django.urls import path

from . import views

urlpatterns = [
    path("dashboard/today/", views.TodayView.as_view()),
    path("planner/suggest/", views.PlannerSuggestView.as_view()),
    path("planner/apply/", views.PlannerApplyView.as_view()),
]
