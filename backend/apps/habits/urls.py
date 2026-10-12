from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("habits", views.HabitViewSet, basename="habit")

urlpatterns = router.urls
