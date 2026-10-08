"""Update existing AI Gateway keys with their creator's user id."""

from django.core.management.base import BaseCommand, CommandError

from ai_gateway.client import AIGatewayClient
from ai_gateway.exceptions import AIGatewayError
from ai_gateway.models import Key


class Command(BaseCommand):
    help = "Update AI Gateway keys with the Entra ID of their creator."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count eligible keys without making AI Gateway requests.",
        )

    def handle(self, *args, **options):
        keys = Key.objects.select_related("created_by").order_by("pk")
        keys_without_creator = keys.filter(created_by__isnull=True).count()
        keys_to_update = keys.filter(created_by__isnull=False)
        total = keys_to_update.count()

        if options["dry_run"]:
            self.stdout.write(
                f"Dry run: {total} key(s) would be updated; "
                f"{keys_without_creator} key(s) without a creator would be skipped."
            )
            return

        client = AIGatewayClient.from_settings()
        updated = 0
        failed = 0
        try:
            for key in keys_to_update.iterator(chunk_size=500):
                try:
                    client.update_key_user_id(key.litellm_token, str(key.created_by.oid))
                except AIGatewayError as error:
                    failed += 1
                    self.stderr.write(self.style.ERROR(f"Failed to update key {key.pk}: {error}"))
                else:
                    updated += 1
        finally:
            client.close()

        self.stdout.write(
            f"Updated {updated} key(s); skipped {keys_without_creator} key(s) without a creator; "
            f"failed {failed} key(s)."
        )
        if failed:
            raise CommandError(f"Failed to update {failed} of {total} AI Gateway key(s).")
