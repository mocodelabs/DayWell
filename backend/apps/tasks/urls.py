from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("tasks", views.TaskViewSet, basename="task")
router.register("categories", views.CategoryViewSet, basename="category")

subtasks = views.SubtaskViewSet.as_view({"get": "list", "post": "create"})
subtask = views.SubtaskViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"})

urlpatterns = [
    *router.urls,
    path("tasks/<int:task_pk>/subtasks/", subtasks),
    path("tasks/<int:task_pk>/subtasks/<int:pk>/", subtask),
]
