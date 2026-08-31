"""
Make `auth.User.email` a real identity: required and unique.

`auth.User` belongs to `django.contrib.auth`, not to us -- we cannot add
`unique=True` to its `email` field by editing the model. So this migration
enforces uniqueness the only way available to a non-owned model: a unique
index created directly on `auth_user` with raw SQL, living in *our* app
instead of Django's. Application-level requiredness and format checks live
in `authentication.views.register` (backed by `authentication.emails`);
this index is the backstop that makes a race between two concurrent
registrations impossible to win with a duplicate.

Email is treated as case-insensitive: `Brian@example.com` and
`brian@example.com` are the same mailbox to a human, and letting them
collide silently was step 1 of this whole change. Both this migration and
`authentication.emails.normalize_email` lowercase the full address before
comparing or storing it, so the index (built on the literal `email` column)
and the application check (`User.objects.filter(email=normalized_value)`)
always agree on what "the same address" means -- there is no functional
`LOWER(email)` index to drift out of sync with the Python side.

Existing rows are handled before the index is created:

* A blank email gets a deterministic placeholder on the `.invalid` TLD
  (RFC 2606, reserved so it can never be mistaken for a deliverable
  address) -- `user-<id>@no-email.invalid`. Nothing is lost, the index can
  still be created, and "which accounts still need a real email" is just
  `email__endswith="@no-email.invalid"`.
* Two accounts that would collide once normalised are NOT silently
  renamed -- quietly mangling a real address is worse than stopping and
  telling the operator what to fix, because the person whose address
  changed would never know. The migration raises, naming every conflicting
  address and the usernames that share it, and no changes are applied
  (Postgres runs migrations inside a transaction, so a raised exception
  rolls back both the backfill and the index creation together).
"""
from django.conf import settings
from django.db import migrations

PLACEHOLDER_DOMAIN = "no-email.invalid"

UNIQUE_INDEX_SQL = "CREATE UNIQUE INDEX auth_user_email_unique ON auth_user (email);"
DROP_UNIQUE_INDEX_SQL = "DROP INDEX IF EXISTS auth_user_email_unique;"


def backfill_and_normalize_emails(apps, schema_editor):
    User = apps.get_model("auth", "User")

    # This is a data migration: it must not import application code that
    # can change independently of this historical migration, so the
    # lowercasing rule is repeated here rather than imported from
    # `authentication.emails.normalize_email`. Keep the two in sync by hand.
    for user in User.objects.all().order_by("pk"):
        current = user.email or ""
        stripped = current.strip()
        normalized = f"user-{user.pk}@{PLACEHOLDER_DOMAIN}" if not stripped else stripped.lower()
        if normalized != current:
            user.email = normalized
            user.save(update_fields=["email"])

    by_email = {}
    for email, username in User.objects.values_list("email", "username").order_by("pk"):
        by_email.setdefault(email, []).append(username)

    duplicates = {email: usernames for email, usernames in by_email.items() if len(usernames) > 1}
    if duplicates:
        details = "; ".join(
            f"{email!r} shared by {', '.join(usernames)}"
            for email, usernames in sorted(duplicates.items())
        )
        raise RuntimeError(
            "Cannot make auth_user.email unique: the following addresses are shared by more than one "
            f"account and must be resolved by hand before this migration can run: {details}"
        )


def reverse_backfill(apps, schema_editor):
    # Deliberately a no-op. Lowercasing and placeholder assignment are not
    # invertible -- we did not record which rows were blank or what case
    # they originally used -- so "reversing" this step can only mean
    # letting `migrate authentication zero` proceed without crashing.
    # Actual reversibility (dropping the constraint the forward migration
    # added) is handled by the RunSQL step below, which is fully invertible.
    pass


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(backfill_and_normalize_emails, reverse_backfill),
        migrations.RunSQL(sql=UNIQUE_INDEX_SQL, reverse_sql=DROP_UNIQUE_INDEX_SQL),
    ]
