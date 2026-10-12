from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("reminders", views.ReminderViewSet, basename="reminder")
router.register("alarms", views.AlarmViewSet, basename="alarm")
router.register("notifications", views.NotificationViewSet, basename="notification")

urlpatterns = [
    *router.urls,
    path("push/config/", views.PushConfigView.as_view()),
    path("push/subscriptions/", views.PushSubscriptionView.as_view()),
    path("push/subscriptions/<int:pk>/", views.PushSubscriptionDetailView.as_view()),
    path("push/unsubscribe/", views.PushUnsubscribeByEndpointView.as_view()),
    path("push/receipt/", views.PushReceiptView.as_view()),
]
