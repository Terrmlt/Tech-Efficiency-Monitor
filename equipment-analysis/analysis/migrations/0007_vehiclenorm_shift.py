from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('analysis', '0006_vehiclenorm'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='vehiclenorm',
            unique_together=set(),
        ),
        migrations.AddField(
            model_name='vehiclenorm',
            name='shift',
            field=models.PositiveSmallIntegerField(
                null=True, blank=True, verbose_name='Смена'
            ),
        ),
        migrations.AlterUniqueTogether(
            name='vehiclenorm',
            unique_together={('report', 'vehicle_name', 'shift')},
        ),
    ]
