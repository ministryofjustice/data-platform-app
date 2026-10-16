import pytest

from support_assistant.retrieval import build_search_query, search_guide


class TestBuildSearchQuery:
    def test_returns_none_without_words(self):
        assert build_search_query("?! ...") is None

    def test_treats_tsquery_syntax_as_plain_words(self):
        assert build_search_query("key & !model | (budget)") is not None


@pytest.mark.django_db
class TestSearchGuide:
    def test_returns_most_relevant_chunk_first(self, guide_chunks):
        results = search_guide("How do I create an API key?", top_k=3, min_rank=0)

        assert results[0] == guide_chunks[0]

    def test_matches_any_word_in_question(self, guide_chunks):
        results = search_guide("budget zebra", top_k=3, min_rank=0)

        assert results == [guide_chunks[2]]

    def test_limits_to_top_k(self, guide_chunks):
        assert len(search_guide("gateway key models budget", top_k=1, min_rank=0)) == 1

    def test_excludes_chunks_below_min_rank(self, guide_chunks):
        assert search_guide("create key", top_k=3, min_rank=100) == []

    def test_returns_nothing_for_unrelated_question(self, guide_chunks):
        assert search_guide("what is the weather in Leeds", min_rank=0) == []

    def test_returns_nothing_for_stop_words_only(self, guide_chunks):
        assert search_guide("what is the", min_rank=0) == []

    def test_uses_settings_defaults(self, guide_chunks, settings):
        settings.SUPPORT_ASSISTANT_TOP_K = 1
        settings.SUPPORT_ASSISTANT_MIN_RANK = 0

        assert len(search_guide("gateway key models budget")) == 1
