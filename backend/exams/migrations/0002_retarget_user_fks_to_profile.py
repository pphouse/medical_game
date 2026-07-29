# Hand-written: retarget user FKs to accounts.Profile (UUID PK). See
# quiz/migrations/0003_retarget_user_fks_to_profile.py for the rationale.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_profile"),
        ("exams", "0001_initial"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="mockresult",
            unique_together=set(),
        ),
        migrations.AlterUniqueTogether(
            name="monthlyranking",
            unique_together=set(),
        ),
        migrations.RemoveField(model_name="mockresult", name="user"),
        migrations.RemoveField(model_name="monthlyranking", name="user"),
        migrations.AddField(
            model_name="mockresult",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="mock_results",
                to="accounts.profile",
            ),
        ),
        migrations.AddField(
            model_name="monthlyranking",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="monthly_rankings",
                to="accounts.profile",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="mockresult",
            unique_together={("user", "mock_exam")},
        ),
        migrations.AlterUniqueTogether(
            name="monthlyranking",
            unique_together={("user", "month")},
        ),
    ]
