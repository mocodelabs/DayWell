from django.urls import path

from . import views

urlpatterns = [
    path("billing/", views.BillingView.as_view()),
    path("billing/checkout/", views.CheckoutView.as_view()),
    path("billing/verify/", views.VerifyView.as_view()),
    path("billing/cancel-renewal/", views.CancelRenewalView.as_view()),
    path("billing/webhook/paystack/", views.webhook),
]
