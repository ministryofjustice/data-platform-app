import httpx
import pytest

from support_assistant.models import Interaction
from support_assistant.services import NO_ANSWER, build_messages, cited_sources, is_declined
from support_assistant.services import answer_question as ask


class TestIsDeclined:
    @pytest.mark.parametrize("answer", ["", "  ", NO_ANSWER, f"{NO_ANSWER}."])
    def test_declined(self, answer):
        assert is_declined(answer)

    def test_not_declined(self):
        assert not is_declined("Choose create key [1].")


@pytest.mark.django_db
class TestBuildMessages:
    def test_includes_numbered_extracts_and_question(self, guide_chunks):
        messages = build_messages("How do I create a key?", guide_chunks[:2])

        assert messages[0]["role"] == "system"
        assert NO_ANSWER in messages[0]["content"]
        user_content = messages[1]["content"]
        assert '<extract number="1" title="AI Gateway: Create an API key">' in user_content
        assert '<extract number="2"' in user_content
        assert user_content.endswith("Question:\nHow do I create a key?")


@pytest.mark.django_db
class TestCitedSources:
    def test_returns_only_cited_sources(self, guide_chunks):
        sources = cited_sources("See [2].", guide_chunks)

        assert sources == [{"title": "AI Gateway: Available models", "url": guide_chunks[1].url}]

    def test_returns_all_sources_when_none_cited(self, guide_chunks):
        assert len(cited_sources("No citations.", guide_chunks)) == 3

    def test_deduplicates_by_url(self, make_chunk):
        chunks = [
            make_chunk("Part", "One", url="https://guide.test/a"),
            make_chunk("Part", "Two", url="https://guide.test/a"),
        ]

        assert len(cited_sources("[1] [2]", chunks)) == 1

    def test_uses_heading_alone_for_page_level_chunks(self, make_chunk):
        chunk = make_chunk("Keys", "Text", page_title="Keys")

        assert cited_sources("[1]", [chunk])[0]["title"] == "Keys"


@pytest.mark.django_db
class TestAnswerQuestion:
    def test_answers_from_retrieved_extracts(self, user, guide_chunks, gateway, settings):
        settings.SUPPORT_ASSISTANT_MIN_RANK = 0

        interaction = ask(user, "How do I create an API key?")

        assert interaction.pk is not None
        assert interaction.outcome == Interaction.Outcome.ANSWERED
        assert interaction.answer == "Choose create key [1]."
        assert interaction.sources == [
            {"title": "AI Gateway: Create an API key", "url": guide_chunks[0].url}
        ]
        assert interaction.retrieved_chunks[0]["id"] == guide_chunks[0].pk
        assert interaction.model == "test-model"
        assert interaction.user == user
        assert "Go to your project" in gateway.requests[0]["messages"][1]["content"]

    def test_falls_back_without_calling_gateway_when_nothing_matches(
        self, user, guide_chunks, gateway
    ):
        interaction = ask(user, "What is the weather in Leeds?")

        assert interaction.outcome == Interaction.Outcome.NO_MATCH
        assert interaction.answer == ""
        assert gateway.requests == []

    def test_records_declined_answer(self, user, guide_chunks, gateway, settings):
        settings.SUPPORT_ASSISTANT_MIN_RANK = 0
        gateway.answer = NO_ANSWER

        interaction = ask(user, "Can I create a key for my cat?")

        assert interaction.outcome == Interaction.Outcome.DECLINED
        assert interaction.answer == ""
        assert interaction.sources == []

    def test_records_gateway_error(self, user, guide_chunks, gateway, settings):
        settings.SUPPORT_ASSISTANT_MIN_RANK = 0
        gateway.handler = lambda request: httpx.Response(500, text="Internal error")

        interaction = ask(user, "How do I create a key?")

        assert interaction.outcome == Interaction.Outcome.ERROR

    def test_records_error_when_not_configured(self, user, guide_chunks, settings):
        settings.SUPPORT_ASSISTANT_MIN_RANK = 0
        settings.SUPPORT_ASSISTANT_API_KEY = None

        interaction = ask(user, "How do I create a key?")

        assert interaction.outcome == Interaction.Outcome.ERROR
