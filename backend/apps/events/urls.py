from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("calendar/events", views.EventViewSet, basename="event")

urlpatterns = router.urls
