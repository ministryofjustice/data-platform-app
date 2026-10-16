from django.conf import settings
from django.core.cache import cache
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from data_platform_app.mixins import FeatureRequiredMixin
from support_assistant.forms import FeedbackForm, QuestionForm
from support_assistant.models import Feedback, Interaction
from support_assistant.services import answer_question

RATE_LIMIT_MESSAGE = "You have asked a lot of questions recently. Try again in a few minutes."


def is_rate_limited(user) -> bool:
    """Count a question against the user's fixed-window allowance and report if it is exceeded.

    Uses the default Django cache, so limits are only shared across processes when a shared
    cache backend is configured.
    """
    key = f"support_assistant:questions:{user.pk}"
    window = settings.SUPPORT_ASSISTANT_RATE_LIMIT_WINDOW
    cache.add(key, 0, timeout=window)
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=window)
        count = 1
    return count > settings.SUPPORT_ASSISTANT_RATE_LIMIT


def assistant_context(**extra):
    return {
        "user_guide_url": settings.SUPPORT_ASSISTANT_GUIDE_BASE_URL,
        **extra,
    }


class AskView(FeatureRequiredMixin, View):
    """Answer a question from the landing page chat, as an HTMX fragment or a full page."""

    feature_flag = "SUPPORT_ASSISTANT"
    http_method_names = ["post"]

    def post(self, request):
        form = QuestionForm(request.POST)
        if not form.is_valid():
            return self.render_result(form, status=400, error_message=form.errors["question"][0])
        if is_rate_limited(request.user):
            return self.render_result(form, status=429, error_message=RATE_LIMIT_MESSAGE)

        interaction = answer_question(request.user, form.cleaned_data["question"])
        return self.render_result(form, interaction=interaction)

    def render_result(self, form, status=200, **extra):
        context = assistant_context(**extra)
        if self.request.htmx:
            # HTMX only swaps 2xx responses, so errors are returned as 200 fragments
            return render(self.request, "includes/support_assistant/_answer.html", context)
        return render(
            self.request,
            "support_assistant/answer.html",
            {**context, "form": form},
            status=status,
        )


class FeedbackView(FeatureRequiredMixin, View):
    """Record whether an answer helped. Users can only rate their own interactions."""

    feature_flag = "SUPPORT_ASSISTANT"
    http_method_names = ["post"]

    def post(self, request, pk):
        interaction = get_object_or_404(Interaction, pk=pk, user=request.user)
        form = FeedbackForm(request.POST)
        if not form.is_valid():
            if request.htmx:
                error_message = next(iter(form.errors.values()))[0]
                return self.render_feedback(interaction, error_message=error_message)
            return redirect("landing")

        feedback, _ = Feedback.objects.update_or_create(
            interaction=interaction,
            defaults={
                "helpful": form.cleaned_data["helpful"],
                "comment": form.cleaned_data["comment"],
            },
        )
        if request.htmx:
            return self.render_feedback(interaction, feedback=feedback)
        return redirect("landing")

    def render_feedback(self, interaction, **extra):
        return render(
            self.request,
            "includes/support_assistant/_feedback.html",
            assistant_context(interaction=interaction, **extra),
        )
