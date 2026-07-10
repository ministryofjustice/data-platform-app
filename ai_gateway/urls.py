from django.urls import path

from ai_gateway.views import KeyCreatedView, KeyCreateView, KeyListView

app_name = "ai_gateway"

urlpatterns = [
    path("keys/", KeyListView.as_view(), name="key_list"),
    path("keys/create/", KeyCreateView.as_view(), name="key_create"),
    path("keys/created/", KeyCreatedView.as_view(), name="key_created"),
]
