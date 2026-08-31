"""
Management command to create a superuser from environment variables.
"""
import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from authentication.emails import normalize_email

User = get_user_model()


class Command(BaseCommand):
    help = "Create a superuser from environment variables if it doesn't exist"

    def handle(self, *args, **options):
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "admin")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "admin")

        # This is the other entry point that creates a `User` row (the
        # register view is the first). Email must be normalised the same
        # way here as everywhere else -- see authentication/emails.py --
        # or an operator-supplied `DJANGO_SUPERUSER_EMAIL` in a different
        # case than an existing account's could slip past the database's
        # unique index and create two accounts for one mailbox.
        email = normalize_email(os.environ.get("DJANGO_SUPERUSER_EMAIL", "admin@example.com"))
        if not email:
            raise CommandError("DJANGO_SUPERUSER_EMAIL must not be blank -- email is a required identity.")

        if User.objects.filter(username=username).exists():
            self.stdout.write(
                self.style.SUCCESS(f"Superuser '{username}' already exists. Skipping.")
            )
            return

        User.objects.create_superuser(
            username=username,
            email=email,
            password=password,
        )

        self.stdout.write(
            self.style.SUCCESS(f"Superuser '{username}' created successfully.")
        )
