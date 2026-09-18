"""
Finish `EvaluationLog.result`'s boolean -> string type change.

The previous migration backfilled `result_tmp` from the boolean `result`
column. This one drops the boolean column and renames `result_tmp` into its
place, now that every row has the correct "true"/"false" string.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sdk_api", "0004_evaluationlog_result_backfill"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="evaluationlog",
            name="result",
        ),
        migrations.RenameField(
            model_name="evaluationlog",
            old_name="result_tmp",
            new_name="result",
        ),
        migrations.AlterField(
            model_name="evaluationlog",
            name="result",
            field=models.CharField(max_length=255),
        ),
    ]
