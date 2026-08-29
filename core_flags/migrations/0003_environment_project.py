import django.db.models.deletion
from django.db import migrations, models


def backfill_default_project(apps, schema_editor):
    """
    Assign every existing NULL-project Environment to one Default project.

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
