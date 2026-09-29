"""
`manage.py telemetry --show` prints the exact payload this installation would
send, without sending it. `--send` sends it right now, for validating a
collector end to end.
"""
import json

from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError
from django.utils import timezone

from telemetry.models import SINGLETON_ID, InstallationIdentity
from telemetry.payload import build_payload
from telemetry.sender import post
from telemetry.settings import is_enabled, telemetry_url


class Command(BaseCommand):
    help = "Inspect the anonymous telemetry this installation sends."

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group()
        group.add_argument("--show", action="store_true", help="Print the payload as JSON without sending it.")
        group.add_argument("--send", action="store_true", help="Send the payload now, ignoring the daily window.")

    def handle(self, *args, **options):
        if options["show"]:
            self.stdout.write(json.dumps(self._build(self._preview_identity()), indent=2))
        elif options["send"]:
            self._send()
        else:
            self.print_help("manage.py", "telemetry")

    def _send(self):
        if not is_enabled():
            self.stdout.write("Telemetry is disabled (FLAGWARD_TELEMETRY / CI); nothing was sent.")
            return
        identity = InstallationIdentity.get_or_create_singleton()
        payload = self._build(identity)
        # Stamped whatever the outcome, like the background loop: a manual send
        # counts as today's heartbeat.
        InstallationIdentity.objects.filter(id=SINGLETON_ID).update(last_sent_at=timezone.now())
        try:
            status = post(payload)
        except Exception as error:  # noqa: BLE001 -- report any failure to the operator
            self.stderr.write(f"Send to {telemetry_url()} failed: {error}")
            return
        self.stdout.write(f"Sent to {telemetry_url()}: HTTP {status}")

    def _build(self, identity: InstallationIdentity) -> dict:
        try:
            return build_payload(identity)
        except DatabaseError as error:
            raise CommandError(f"Database schema is out of date ({error}); run `manage.py migrate`.") from error

    def _preview_identity(self) -> InstallationIdentity:
        """
        The persisted identity when there is one. Otherwise an unsaved
        stand-in: previewing must never create the row, since with telemetry
        off no identity may exist at all.
        """
        try:
            return InstallationIdentity.objects.filter(id=SINGLETON_ID).first() or InstallationIdentity()
        except DatabaseError:
            self.stderr.write("Telemetry table not found; run `manage.py migrate`. Showing a preview identity.")
            return InstallationIdentity()
