from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("notification-preferences", views.NotificationPreferenceViewSet, basename="notification-preference")

urlpatterns = [
    path("preferences/", views.PreferenceView.as_view()),
    path("preferences/sounds/", views.SoundListView.as_view()),
    *router.urls,
]
