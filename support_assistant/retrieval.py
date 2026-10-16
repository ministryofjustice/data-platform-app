"""Find user guide sections relevant to a question using Postgres full-text search."""

import re

from django.conf import settings
from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db.models import F

from support_assistant.models import GuideChunk

MAX_QUERY_TERMS = 30


def build_search_query(question: str) -> SearchQuery | None:
    """Build an OR query from the words in a question.

    Each word is passed to Postgres as a plain query, so user input is never parsed as
    tsquery syntax. Matching any word keeps recall high; ranking rewards matching more.
    """
    words = list(dict.fromkeys(re.findall(r"\w+", question.lower())))[:MAX_QUERY_TERMS]
    query = None
    for word in words:
        term = SearchQuery(word, config="english")
        query = term if query is None else query | term
    return query


def search_guide(
    question: str, top_k: int | None = None, min_rank: float | None = None
) -> list[GuideChunk]:
    """Return the most relevant guide chunks whose rank meets the minimum threshold."""
    top_k = settings.SUPPORT_ASSISTANT_TOP_K if top_k is None else top_k
    min_rank = settings.SUPPORT_ASSISTANT_MIN_RANK if min_rank is None else min_rank
    query = build_search_query(question)
    if query is None:
        return []
    return list(
        GuideChunk.objects.filter(search_vector=query)
        .annotate(rank=SearchRank(F("search_vector"), query))
        .filter(rank__gte=min_rank)
        .order_by("-rank", "pk")[:top_k]
    )
