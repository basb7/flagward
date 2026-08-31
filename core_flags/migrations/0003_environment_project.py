import django.db.models.deletion
from django.db import migrations, models


def backfill_default_project(apps, schema_editor):
    """
    Assign every existing NULL-project Environment to one Default project.

    This writes rows, and the schema changes that follow it live in 0004 on
    purpose. Postgres defers foreign-key trigger events to the end of a
    transaction, so an ALTER TABLE touching a table this backfill just wrote
    to is refused with "cannot ALTER TABLE ... because it has pending trigger
    events". Django gives each migration its own transaction, so splitting
    them is what lets the events flush before the ALTER runs.

    An empty database never hit this: the early return below means no rows are
    written, no trigger events are pending, and the ALTER succeeds. It only
    fails where it matters -- on a database that already has environments.

    Trivial because the project is pre-release: at most one Organization and
    one Project are created, and only if a null row actually exists. No
    membership row is created — on a fresh boot `migrate` runs before any
    User exists to attribute one to (compose.yml runs `create_super_user`
    after `migrate`), so a migration that assumed a User would fail there.
    """
    Environment = apps.get_model("core_flags", "Environment")
    Organization = apps.get_model("tenancy", "Organization")
    Project = apps.get_model("tenancy", "Project")

    orphaned = Environment.objects.filter(project__isnull=True)
    if not orphaned.exists():
        return

    organization = Organization.objects.create(name="Default", plan="COMMUNITY")
    project = Project.objects.create(organization=organization, name="Default", key="default")
    orphaned.update(project=project)


class Migration(migrations.Migration):

    dependencies = [
        ("core_flags", "0002_alter_featureflag_options_alter_flagoverride_options_and_more"),
        ("tenancy", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="environment",
            name="project",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="environments",
                to="tenancy.project",
            ),
        ),
        migrations.RunPython(backfill_default_project, migrations.RunPython.noop),
    ]
