"""
Make `Environment.project` required, in its own transaction.

These two operations were the tail of 0003, after its RunPython backfill. On a
populated database that ordering fails: the backfill writes rows referencing
`tenancy_project`, Postgres holds the foreign-key trigger events until the
transaction commits, and the ALTER TABLE below is then refused with "cannot
ALTER TABLE ... because it has pending trigger events".

An empty database never reached it -- the backfill returns early when there is
nothing to fill, so no events are pending. The failure was reserved for
exactly the case the backfill exists to serve.

Splitting them is the fix rather than making the migration non-atomic: each
migration gets its own transaction, the events flush when 0003 commits, and a
failure here still leaves 0003's work committed rather than half-applied.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core_flags", "0003_environment_project"),
    ]

    operations = [
        migrations.AlterField(
            model_name="environment",
            name="project",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="environments",
                to="tenancy.project",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="environment",
            unique_together={("project", "key")},
        ),
    ]
