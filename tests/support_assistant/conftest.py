import pytest
from django.contrib.postgres.search import SearchVector
from model_bakery import baker

from support_assistant.models import GuideChunk


@pytest.fixture
def make_chunk(db):
    """Factory for indexed guide chunks."""

    def _make_chunk(heading, content, page_title="AI Gateway", **kwargs):
        chunk = baker.make(
            GuideChunk,
            page_title=page_title,
            heading=heading,
            content=content,
            url=kwargs.pop("url", f"https://user-guide.test/{heading.lower().replace(' ', '-')}"),
            **kwargs,
        )
        GuideChunk.objects.filter(pk=chunk.pk).update(
            search_vector=SearchVector("page_title", weight="A", config="english")
            + SearchVector("heading", weight="A", config="english")
            + SearchVector("content", weight="B", config="english")
        )
        return chunk

    return _make_chunk


@pytest.fixture
def guide_chunks(make_chunk):
    return [
        make_chunk(
            "Create an API key",
            "Go to your project, select AI Gateway keys and choose create key.",
        ),
        make_chunk(
            "Available models",
            "The gateway offers models from OpenAI and Anthropic through access groups.",
        ),
        make_chunk("Budgets", "Each team has a monthly budget of 500 pounds."),
    ]


@pytest.fixture
def gateway():
    """Serve the support assistant's gateway calls from a configurable handler.

    Set ``gateway.handler`` to a function taking an ``httpx.Request``; by default it answers
    with ``gateway.answer``. Requests made are recorded in ``gateway.requests``.
    """
    import json
    from types import SimpleNamespace
    from unittest.mock import patch

    import httpx

    from support_assistant.client import ChatCompletionsClient

    state = SimpleNamespace(answer="Choose create key [1].", requests=[], handler=None)

    def default_handler(request):
        return httpx.Response(
            200, json={"choices": [{"message": {"role": "assistant", "content": state.answer}}]}
        )

    def handle(request):
        state.requests.append(json.loads(request.read()))
        return (state.handler or default_handler)(request)

    def build():
        return ChatCompletionsClient(
            base_url="http://ai-gateway.test",
            api_key="sk-test",
            model="test-model",
            client=httpx.Client(
                base_url="http://ai-gateway.test", transport=httpx.MockTransport(handle)
            ),
        )

    with patch(
        "support_assistant.services.ChatCompletionsClient.from_settings", side_effect=build
    ):
        yield state
