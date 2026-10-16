"""Download the AI Gateway user guide from GitHub and rebuild the search index."""

from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError

from support_assistant.exceptions import GuideFetchError
from support_assistant.guide import GitHubGuideSource, sync_user_guide


class Command(BaseCommand):
    help = "Sync the AI Gateway user guide from GitHub into the support assistant index."

    def handle(self, *args, **options):
        try:
            source = GitHubGuideSource.from_settings()
        except ImproperlyConfigured as error:
            raise CommandError(str(error)) from error
        try:
            result = sync_user_guide(source)
        except (GuideFetchError, ImproperlyConfigured) as error:
            raise CommandError(str(error)) from error
        finally:
            source.close()

        self.stdout.write(
            self.style.SUCCESS(
                f"Synced {result.files} file(s): {result.created} created, "
                f"{result.updated} updated, {result.deleted} deleted."
            )
        )
