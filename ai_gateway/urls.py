from django.urls import path

from ai_gateway.views import (
    KeyCreateConfirmView,
    KeyCreateView,
    KeyDetailView,
    KeyListView,
    KeyRegenerateView,
    KeyRevokeView,
    UsageByAPIKeyView,
    UsageByModelView,
    UsageView,
)

app_name = "ai_gateway"

urlpatterns = [
    path("usage/", UsageView.as_view(), name="usage"),
    path("usage/api-keys/", UsageByAPIKeyView.as_view(), name="usage_by_key"),
    path("usage/models/", UsageByModelView.as_view(), name="usage_by_model"),
    path("keys/", KeyListView.as_view(), name="key_list"),
    path("keys/create/", KeyCreateView.as_view(), name="key_create"),
    path("keys/create/confirm/", KeyCreateConfirmView.as_view(), name="key_create_confirm"),
    path("keys/<int:pk>/", KeyDetailView.as_view(), name="key_detail"),
    path("keys/<int:pk>/regenerate/", KeyRegenerateView.as_view(), name="key_regenerate"),
    path("keys/<int:pk>/revoke/", KeyRevokeView.as_view(), name="key_revoke"),
]
