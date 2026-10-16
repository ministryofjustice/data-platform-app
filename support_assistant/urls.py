from django.urls import path

from support_assistant.views import AskView, FeedbackView

app_name = "support_assistant"

urlpatterns = [
    path("ask/", AskView.as_view(), name="ask"),
    path(
        "interactions/<int:pk>/feedback/",
        FeedbackView.as_view(),
        name="feedback",
    ),
]
