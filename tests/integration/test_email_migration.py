"""
Tests for authentication/migrations/0001_email_required_unique.py.

The backfill and duplicate-refusal behaviour only exist at migration time --
by the time any other test in this suite runs, the migration (and its
unique index) is already applied to the test database, so those two
behaviours cannot be exercised through the ORM the way the rest of the
suite is. These tests migrate the `authentication` app back to the state
just before 0001, seed rows directly against the historical `auth.User`
model, then migrate forward again and assert on the result -- the standard
recipe for testing data migrations with pytest-django
(`transaction=True` is required so the executor's own migration
transactions are not nested inside pytest-django's per-test transaction).

Every test restores the migration to its normal forward-applied state
before returning control, since every other test in the suite assumes
`authentication.0001_email_required_unique` is applied.
"""
import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

MIGRATE_FROM = [("authentication", None)]
MIGRATE_TO = [("authentication", "0001_email_required_unique")]

User = get_user_model()


def _migrate(target):
    # The migration declares no model-state changes (it only runs RunPython
    # data changes and a raw-SQL index), so `auth.User`'s Python class is
    # identical before and after 0001 -- the real, current model can be used
    # to seed and read rows in both states instead of reconstructing a
    # historical `apps` registry for a migration that never touches state.
    MigrationExecutor(connection).migrate(target)


@pytest.mark.django_db(transaction=True)
class TestBlankEmailIsBackfilled:
    def test_a_blank_email_gets_a_placeholder_on_the_invalid_tld(self):
        _migrate(MIGRATE_FROM)
        try:
            user = User.objects.create(username="blankmail", email="", password="x")

            _migrate(MIGRATE_TO)

            refreshed = User.objects.get(pk=user.pk)
            assert refreshed.email == f"user-{user.pk}@no-email.invalid"
            assert refreshed.email.endswith(".invalid")
        finally:
            _migrate(MIGRATE_TO)


@pytest.mark.django_db(transaction=True)
class TestDuplicateEmailsRefuseToMigrate:
    def test_a_case_variant_duplicate_pair_aborts_the_migration_and_names_the_conflict(self):
        _migrate(MIGRATE_FROM)
        try:
            User.objects.create(username="first", email="Brian@Example.com", password="x")
            User.objects.create(username="second", email="brian@example.com", password="x")

            with pytest.raises(RuntimeError) as excinfo:
                _migrate(MIGRATE_TO)

            message = str(excinfo.value)
            assert "brian@example.com" in message
            assert "first" in message
            assert "second" in message

            # Nothing was applied: the index was never created, and neither
            # row was renamed to "fix" the conflict for them.
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM pg_indexes WHERE indexname = 'auth_user_email_unique'"
                )
                assert cursor.fetchone()[0] == 0
            emails = set(
                User.objects.filter(username__in=["first", "second"]).values_list("email", flat=True)
            )
            assert emails == {"Brian@Example.com", "brian@example.com"}
        finally:
            User.objects.filter(username__in=["first", "second"]).delete()
            _migrate(MIGRATE_TO)
