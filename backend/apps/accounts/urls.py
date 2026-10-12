from django.urls import path

from . import views

urlpatterns = [
    path("auth/csrf/", views.CsrfView.as_view()),
    path("auth/register/", views.RegisterView.as_view()),
    path("auth/login/", views.LoginView.as_view()),
    path("auth/logout/", views.LogoutView.as_view()),
    path("auth/me/", views.MeView.as_view()),
    path("auth/password/change/", views.PasswordChangeView.as_view()),
    path("auth/password/reset/", views.PasswordResetRequestView.as_view()),
    path("auth/password/reset/confirm/", views.PasswordResetConfirmView.as_view()),
    path("auth/email/verify/", views.EmailVerifyView.as_view()),
    path("auth/email/verify/resend/", views.EmailVerifyResendView.as_view()),
    path("auth/sessions/", views.SessionListView.as_view()),
    path("auth/sessions/<str:session_key>/", views.SessionRevokeView.as_view()),
    path("account/export/", views.ExportView.as_view()),
    path("account/delete/", views.AccountDeleteView.as_view()),
]
