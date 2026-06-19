from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('analysis', '0003_section_and_new_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='vehiclerecord',
            name='shift',
            field=models.SmallIntegerField(default=0, verbose_name='Смена'),
        ),
    ]
