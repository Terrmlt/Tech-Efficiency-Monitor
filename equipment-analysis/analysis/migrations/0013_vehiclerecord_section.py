from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('analysis', '0012_update_default_norms'),
    ]

    operations = [
        migrations.AddField(
            model_name='vehiclerecord',
            name='section',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='vehicle_records',
                to='analysis.section',
                verbose_name='Участок (переопределение)',
            ),
        ),
    ]
