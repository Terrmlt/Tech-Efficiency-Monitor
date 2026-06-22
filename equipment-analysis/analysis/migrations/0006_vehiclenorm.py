from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('analysis', '0005_alter_vehiclerecord_date'),
    ]

    operations = [
        migrations.CreateModel(
            name='VehicleNorm',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('vehicle_name', models.CharField(max_length=200, verbose_name='Название ТС')),
                ('dumptruck_norm_sec', models.IntegerField(blank=True, null=True, verbose_name='Норма без движения (сек)')),
                ('report', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='vehicle_norms', to='analysis.report', verbose_name='Отчёт')),
            ],
            options={
                'verbose_name': 'Индивидуальная норма ТС',
                'verbose_name_plural': 'Индивидуальные нормы ТС',
                'unique_together': {('report', 'vehicle_name')},
            },
        ),
    ]
