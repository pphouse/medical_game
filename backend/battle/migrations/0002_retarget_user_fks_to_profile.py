# Hand-written: retarget user FKs to accounts.Profile (UUID PK). See
# quiz/migrations/0003_retarget_user_fks_to_profile.py for the rationale.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_profile"),
        ("battle", "0001_initial"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="battleparticipant",
            unique_together=set(),
        ),
        migrations.RemoveField(model_name="battleroom", name="host"),
        migrations.RemoveField(model_name="battleparticipant", name="user"),
        migrations.RemoveField(model_name="battleanswer", name="user"),
        migrations.AddField(
            model_name="battleroom",
            name="host",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="hosted_battle_rooms",
                to="accounts.profile",
            ),
        ),
        migrations.AddField(
            model_name="battleparticipant",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="battle_participations",
                to="accounts.profile",
            ),
        ),
        migrations.AddField(
            model_name="battleanswer",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="battle_answers",
                to="accounts.profile",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="battleparticipant",
            unique_together={("room", "user")},
        ),
    ]
