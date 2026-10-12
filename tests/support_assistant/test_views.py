import pytest
from django.core.cache import cache
from django.urls import reverse
from model_bakery import baker
from pytest_django.asserts import assertContains, assertNotContains, assertTemplateUsed

from support_assistant.models import Feedback, Interaction

ASK_URL = reverse("support_assistant:ask")
HTMX = {"HTTP_HX_REQUEST": "true"}
FALLBACK_MESSAGE = (
    "I couldn't find an answer to that in the user guide. "
    "Please ask your question in the #ask-data-platform Slack channel."
)


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def logged_in_client(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def matching_guide(guide_chunks, settings):
    settings.SUPPORT_ASSISTANT_MIN_RANK = 0
    return guide_chunks


def feedback_url(interaction):
    return reverse("support_assistant:feedback", args=[interaction.pk])


class TestLandingPage:
    def test_shows_chat_when_flag_enabled(self, logged_in_client):
        response = logged_in_client.get(reverse("landing"))

        assertContains(response, "Ask about the AI Gateway")
        assertContains(response, f'hx-post="{ASK_URL}"')
        assertContains(response, 'aria-live="polite"')
        assertContains(response, 'data-maxlength="500"')
        assertContains(response, 'name="csrfmiddlewaretoken"')

    def test_hides_chat_when_flag_disabled(self, logged_in_client, settings):
        settings.FEATURE_FLAGS = {**settings.FEATURE_FLAGS, "SUPPORT_ASSISTANT": False}

        response = logged_in_client.get(reverse("landing"))

        assertNotContains(response, "Ask about the AI Gateway")


@pytest.mark.django_db
class TestAskView:
    def test_requires_login(self, client):
        response = client.post(ASK_URL, {"question": "How do I create a key?"})

        assert response.status_code == 302
        assert response.url.startswith(reverse("login"))

    def test_returns_404_when_flag_disabled(self, logged_in_client, settings):
        settings.FEATURE_FLAGS = {**settings.FEATURE_FLAGS, "SUPPORT_ASSISTANT": False}

        response = logged_in_client.post(ASK_URL, {"question": "How do I create a key?"})

        assert response.status_code == 404

    def test_rejects_get(self, logged_in_client):
        assert logged_in_client.get(ASK_URL).status_code == 405

    def test_enforces_csrf(self, user, matching_guide, gateway):
        from django.test import Client

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(user)

        response = csrf_client.post(ASK_URL, {"question": "How do I create a key?"})

        assert response.status_code == 403

    def test_htmx_returns_answer_fragment(self, logged_in_client, matching_guide, gateway):
        response = logged_in_client.post(
            ASK_URL, {"question": "How do I create an API key?"}, **HTMX
        )

        assert response.status_code == 200
        assertTemplateUsed(response, "includes/support_assistant/_answer.html")
        assertTemplateNotUsedBase(response)
        assertContains(response, "Choose create key [1].")
        assertContains(response, "Sources")
        assertContains(response, f'href="{matching_guide[0].url}"')
        assertNotContains(response, "ask-data-platform")
        interaction = Interaction.objects.get()
        assertContains(response, f'hx-post="{feedback_url(interaction)}"')

    def test_escapes_model_output(self, logged_in_client, matching_guide, gateway):
        gateway.answer = "<script>alert(1)</script> [1]"

        response = logged_in_client.post(ASK_URL, {"question": "create key"}, **HTMX)

        assertNotContains(response, "<script>alert(1)</script>")
        assertContains(response, "&lt;script&gt;")

    def test_full_page_fallback_without_htmx(self, logged_in_client, matching_guide, gateway):
        response = logged_in_client.post(ASK_URL, {"question": "How do I create an API key?"})

        assert response.status_code == 200
        assertTemplateUsed(response, "support_assistant/answer.html")
        assertContains(response, "Choose create key [1].")
        assertContains(response, "How do I create an API key?</textarea>")

    def test_shows_fallback_when_no_guide_content_matches(self, logged_in_client, gateway):
        response = logged_in_client.post(ASK_URL, {"question": "Weather in Leeds?"}, **HTMX)

        assertContains(response, FALLBACK_MESSAGE)
        assertNotContains(response, "<a ")
        assertNotContains(response, "Was this answer helpful?")

    def test_shows_fallback_when_model_declines(self, logged_in_client, matching_guide, gateway):
        gateway.answer = "NO_ANSWER"

        response = logged_in_client.post(ASK_URL, {"question": "create key"}, **HTMX)

        assertContains(response, FALLBACK_MESSAGE)
        assertNotContains(response, "Was this answer helpful?")

    def test_shows_unavailable_message_on_gateway_error(
        self, logged_in_client, matching_guide, gateway
    ):
        import httpx

        gateway.handler = lambda request: httpx.Response(503)

        response = logged_in_client.post(ASK_URL, {"question": "create key"}, **HTMX)

        assertContains(response, "support assistant is not available right now")

    def test_rejects_empty_question(self, logged_in_client, gateway):
        response = logged_in_client.post(ASK_URL, {"question": "   "})

        assert response.status_code == 400
        assertContains(response, "Enter a question", status_code=400)
        assert not Interaction.objects.exists()

    def test_rejects_long_question(self, logged_in_client, gateway, settings):
        settings.SUPPORT_ASSISTANT_MAX_QUESTION_LENGTH = 10

        response = logged_in_client.post(ASK_URL, {"question": "x" * 11}, **HTMX)

        assert response.status_code == 200
        assertContains(response, "Question must be 10 characters or fewer")
        assert gateway.requests == []

    def test_rate_limits_per_user(self, logged_in_client, matching_guide, gateway, settings):
        settings.SUPPORT_ASSISTANT_RATE_LIMIT = 2

        for _ in range(2):
            logged_in_client.post(ASK_URL, {"question": "create key"}, **HTMX)
        response = logged_in_client.post(ASK_URL, {"question": "create key"})

        assert response.status_code == 429
        assertContains(response, "asked a lot of questions", status_code=429)
        assert Interaction.objects.count() == 2

    def test_rate_limit_is_per_user(self, client, matching_guide, gateway, settings):
        settings.SUPPORT_ASSISTANT_RATE_LIMIT = 1
        first, second = baker.make("users.User", _quantity=2)

        client.force_login(first)
        client.post(ASK_URL, {"question": "create key"}, **HTMX)
        client.force_login(second)
        response = client.post(ASK_URL, {"question": "create key"}, **HTMX)

        assertNotContains(response, "asked a lot of questions")

    def test_rate_limit_recovers_when_counter_expires(
        self, logged_in_client, matching_guide, gateway, settings, monkeypatch
    ):
        settings.SUPPORT_ASSISTANT_RATE_LIMIT = 1
        monkeypatch.setattr(cache, "incr", _raise_value_error)

        response = logged_in_client.post(ASK_URL, {"question": "create key"}, **HTMX)

        assertNotContains(response, "asked a lot of questions")


def _raise_value_error(*args, **kwargs):
    raise ValueError("Key does not exist")


def assertTemplateNotUsedBase(response):  # noqa: N802
    assert "base/base.html" not in [template.name for template in response.templates]


@pytest.mark.django_db
class TestFeedbackView:
    @pytest.fixture
    def interaction(self, user):
        return baker.make(Interaction, user=user, outcome=Interaction.Outcome.ANSWERED)

    def test_records_helpful_feedback(self, logged_in_client, interaction):
        response = logged_in_client.post(feedback_url(interaction), {"helpful": "yes"}, **HTMX)

        assert response.status_code == 200
        assertContains(response, "Thank you for your feedback")
        assertNotContains(response, "What were you looking for?")
        assert Feedback.objects.get(interaction=interaction).helpful is True

    def test_unhelpful_feedback_asks_for_optional_comment(self, logged_in_client, interaction):
        response = logged_in_client.post(feedback_url(interaction), {"helpful": "no"}, **HTMX)

        assertContains(response, "What were you looking for?")
        assert Feedback.objects.get(interaction=interaction).helpful is False

    def test_records_comment(self, logged_in_client, interaction):
        logged_in_client.post(feedback_url(interaction), {"helpful": "no"}, **HTMX)

        response = logged_in_client.post(
            feedback_url(interaction), {"helpful": "no", "comment": "Rate limits"}, **HTMX
        )

        assertNotContains(response, "What were you looking for?")
        assert Feedback.objects.get(interaction=interaction).comment == "Rate limits"

    def test_rejects_invalid_feedback(self, logged_in_client, interaction):
        response = logged_in_client.post(feedback_url(interaction), {"helpful": "maybe"}, **HTMX)

        assertContains(response, "Choose yes or no")
        assert not Feedback.objects.exists()

    def test_redirects_without_htmx(self, logged_in_client, interaction):
        valid = logged_in_client.post(feedback_url(interaction), {"helpful": "yes"})
        invalid = logged_in_client.post(feedback_url(interaction), {})

        assert valid.status_code == invalid.status_code == 302
        assert valid.url == invalid.url == reverse("landing")
        assert Feedback.objects.get().helpful is True

    def test_cannot_rate_another_users_interaction(self, client, interaction):
        client.force_login(baker.make("users.User"))

        response = client.post(feedback_url(interaction), {"helpful": "yes"}, **HTMX)

        assert response.status_code == 404
        assert not Feedback.objects.exists()

    def test_returns_404_when_flag_disabled(self, logged_in_client, interaction, settings):
        settings.FEATURE_FLAGS = {**settings.FEATURE_FLAGS, "SUPPORT_ASSISTANT": False}

        response = logged_in_client.post(feedback_url(interaction), {"helpful": "yes"})

        assert response.status_code == 404
