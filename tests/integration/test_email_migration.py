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

Every test restores the migration state to fully forward-applied before
returning control, since every other test in the suite assumes the whole
`authentication` app (not just 0001) is migrated. That restore target is
resolved dynamically (`_latest_authentication_migration`) rather than
hardcoded to "0001_email_required_unique" as it once was: 0001 was the
app's only migration at the time, but is no longer its leaf (see
authentication/migrations/0002_password_reset_token.py) -- a hardcoded
restore target here would silently leave later migrations unapplied for
the rest of the test session the first time a new one is added, exactly as
this one did until it was changed to look the leaf up instead.
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


def _latest_authentication_migration():
    """Resolve the app's current leaf migration, whatever it is by now."""
    executor = MigrationExecutor(connection)
    return [node for node in executor.loader.graph.leaf_nodes() if node[0] == "authentication"]


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
            _migrate(_latest_authentication_migration())


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
            #
            # Asked through Django's introspection rather than the database's
            # own catalogue. The migration creates the index with portable SQL
            # and runs inside a transaction on either engine, so this test has
            # nothing PostgreSQL-specific about it -- reading pg_indexes was
            # the only reason it could not run on the SQLite the project falls
            # back to, and a test that only runs in CI is a test whose failures
            # are found late.
            with connection.cursor() as cursor:
                indexes = connection.introspection.get_constraints(cursor, "auth_user")
            assert "auth_user_email_unique" not in indexes
            emails = set(
                User.objects.filter(username__in=["first", "second"]).values_list("email", flat=True)
            )
            assert emails == {"Brian@Example.com", "brian@example.com"}
        finally:
            # Raw SQL, not the ORM: migrating forward past 0001 again would
            # hit this exact same duplicate-email conflict unless the two
            # rows are gone first, so they must be deleted while
            # "authentication" is still rolled back to nothing -- but
            # PasswordResetToken has a CASCADE FK to User, and Django's
            # deletion collector always considers its table regardless of
            # migration state, which does not exist yet at this point. Raw
            # SQL against auth_user sidesteps the collector entirely.
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM auth_user WHERE username IN ('first', 'second')")
            _migrate(_latest_authentication_migration())
