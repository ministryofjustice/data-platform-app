import pytest
from django.urls import reverse
from model_bakery import baker

from support_assistant.models import Feedback, Interaction


@pytest.mark.django_db
class TestAdmin:
    def test_lists_interactions_with_feedback(self, client, superuser):
        interaction = baker.make(
            Interaction, question="How?", outcome=Interaction.Outcome.ANSWERED
        )
        baker.make(Feedback, interaction=interaction, helpful=False)
        client.force_login(superuser)

        changelist = client.get(reverse("admin:support_assistant_interaction_changelist"))
        detail = client.get(
            reverse("admin:support_assistant_interaction_change", args=[interaction.pk])
        )

        assert changelist.status_code == detail.status_code == 200
        assert b"How?" in changelist.content

    def test_guide_chunks_are_read_only(self, client, superuser, make_chunk):
        chunk = make_chunk("Keys", "Create a key")
        client.force_login(superuser)

        changelist = client.get(reverse("admin:support_assistant_guidechunk_changelist"))
        add = client.get(reverse("admin:support_assistant_guidechunk_add"))
        detail = client.get(reverse("admin:support_assistant_guidechunk_change", args=[chunk.pk]))

        assert changelist.status_code == detail.status_code == 200
        assert add.status_code == 403

    def test_model_string_representations(self, make_chunk):
        chunk = make_chunk("Keys", "Create a key", page_title="Guide")
        interaction = baker.make(Interaction, outcome=Interaction.Outcome.NO_MATCH)
        feedback = baker.make(Feedback, interaction=interaction, helpful=True)

        assert str(chunk) == "Guide: Keys"
        assert str(interaction).startswith("No matching guide content at ")
        assert str(feedback) == "Helpful"
        feedback.helpful = False
        assert str(feedback) == "Not helpful"
