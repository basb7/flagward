"""
Migrating `Environment.project` onto a database that already has environments.

This path had no test, and that is exactly where it broke. `core_flags.0003`
originally added the column, backfilled it, and then altered it to NOT NULL in
one migration. On Postgres that is refused:

    cannot ALTER TABLE "tenancy_project" because it has pending trigger events

The backfill writes rows referencing `tenancy_project`, Postgres holds the
foreign-key trigger events until the transaction commits, and the ALTER inside
that same transaction cannot proceed.

An empty database never hit it. The backfill returns early when there is
nothing to fill, so no events are pending and the ALTER succeeds -- which is
why every test and every local run passed while the one case the backfill
exists to serve was broken.

The schema changes now live in `0004`, in their own transaction. These tests
run the migration against a database seeded the way a real one would be, so
the empty-database success can never again stand in for the populated one.

(`transaction=True` is required: the executor's own migrations cannot run
inside the test's outer transaction.)
"""
import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("core_flags", "0002_alter_featureflag_options_alter_flagoverride_options_and_more")]
AFTER = [("core_flags", "0004_environment_project_required")]


def _migrate(target):
    MigrationExecutor(connection).migrate(target)


def _leaf(app):
    executor = MigrationExecutor(connection)
    return [node for node in executor.loader.graph.leaf_nodes() if node[0] == app]


@pytest.mark.django_db(transaction=True)
class TestMigratingAPopulatedDatabase:
    def test_an_existing_environment_survives_and_gains_a_project(self):
        _migrate(BEFORE)
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO core_flags_environment (id, name, key, api_key)"
                " VALUES (gen_random_uuid(), 'Production', 'production', 'seeded-key')"
            )
            cursor.execute(
                "INSERT INTO core_flags_featureflag"
                " (id, environment_id, key, name, is_enabled, flag_type)"
                " SELECT gen_random_uuid(), id, 'new-checkout', 'New checkout', false,"
                " 'BOOLEAN' FROM core_flags_environment"
            )

        # This is the call that used to raise ObjectInUse.
        _migrate(AFTER)

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT e.key, p.name, o.name FROM core_flags_environment e"
                " JOIN tenancy_project p ON p.id = e.project_id"
                " JOIN tenancy_organization o ON o.id = p.organization_id"
            )
            rows = cursor.fetchall()
            cursor.execute("SELECT count(*) FROM core_flags_featureflag")
            flag_count = cursor.fetchone()[0]

        assert rows == [("production", "Default", "Default")]
        assert flag_count == 1, "the environment's flags must survive the backfill"

        _migrate(_leaf("core_flags"))

    def test_the_column_ends_up_required(self):
        _migrate(BEFORE)
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO core_flags_environment (id, name, key, api_key)"
                " VALUES (gen_random_uuid(), 'Staging', 'staging', 'another-key')"
            )

        _migrate(AFTER)

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT is_nullable FROM information_schema.columns"
                " WHERE table_name = 'core_flags_environment'"
                " AND column_name = 'project_id'"
            )
            assert cursor.fetchone()[0] == "NO"

        _migrate(_leaf("core_flags"))

    def test_an_empty_database_still_migrates(self):
        """The path that always worked, kept honest now that it is not the only one."""
        _migrate(BEFORE)

        _migrate(AFTER)

        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM core_flags_environment")
            assert cursor.fetchone()[0] == 0

        _migrate(_leaf("core_flags"))
