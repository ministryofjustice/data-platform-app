from django.urls import path

from ai_gateway.views import (
    KeyCreateConfirmView,
    KeyCreateView,
    KeyDetailView,
    KeyListView,
    KeyModelChangeConfirmView,
    KeyModelChangeView,
    KeyRegenerateView,
    KeyRevokeView,
    UsageView,
)

app_name = "ai_gateway"

urlpatterns = [
    path("usage/", UsageView.as_view(), name="usage"),
    path("keys/", KeyListView.as_view(), name="key_list"),
    path("keys/create/", KeyCreateView.as_view(), name="key_create"),
    path("keys/create/confirm/", KeyCreateConfirmView.as_view(), name="key_create_confirm"),
    path("keys/<int:pk>/", KeyDetailView.as_view(), name="key_detail"),
    path("keys/<int:pk>/models/change/", KeyModelChangeView.as_view(), name="key_model_change"),
    path(
        "keys/<int:pk>/models/change/review/",
        KeyModelChangeConfirmView.as_view(),
        name="key_model_change_review",
    ),
    path("keys/<int:pk>/regenerate/", KeyRegenerateView.as_view(), name="key_regenerate"),
    path("keys/<int:pk>/revoke/", KeyRevokeView.as_view(), name="key_revoke"),
]
