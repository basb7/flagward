"""
Prepare `EvaluationLog.result` for its boolean -> string type change.

A direct `AlterField` from `BooleanField` to `CharField` would not produce the
"true"/"false" strings the new column needs: SQLite copies the raw stored
value ("1"/"0") into the new text column, and PostgreSQL's implicit
boolean->varchar cast produces "t"/"f". Both silently corrupt existing rows.

So the type change happens in two migrations: this one adds a temporary
column and backfills it from the still-present boolean column, and the next
one drops the old column and renames the temporary one into place.
"""
from django.db import migrations, models


def backfill_result_as_string(apps, schema_editor):
    EvaluationLog = apps.get_model("sdk_api", "EvaluationLog")
    EvaluationLog.objects.filter(result=True).update(result_tmp="true")
    EvaluationLog.objects.filter(result=False).update(result_tmp="false")


class Migration(migrations.Migration):

    dependencies = [
        ("sdk_api", "0003_alter_sdkregistration_sdk_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="evaluationlog",
            name="result_tmp",
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.RunPython(backfill_result_as_string, migrations.RunPython.noop),
    ]
