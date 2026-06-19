from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('analysis', '0002_remove_report_bulldozer_idle_norm_pct_and_more'),
    ]

    operations = [
        # 1. New model: Section
        migrations.CreateModel(
            name='Section',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, verbose_name='Название участка')),
            ],
            options={
                'verbose_name': 'Участок',
                'verbose_name_plural': 'Участки',
                'ordering': ['name'],
            },
        ),

        # 2. Report: add section FK
        migrations.AddField(
            model_name='report',
            name='section',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to='analysis.section',
                verbose_name='Участок',
            ),
        ),

        # 3. Report: add year
        migrations.AddField(
            model_name='report',
            name='year',
            field=models.IntegerField(default=2026, verbose_name='Год'),
        ),

        # 4. Report: add shift
        migrations.AddField(
            model_name='report',
            name='shift',
            field=models.SmallIntegerField(
                choices=[(1, 'Смена 1'), (2, 'Смена 2')],
                default=1,
                verbose_name='Смена',
            ),
        ),

        # 5. Report: update daily_norm_sec default (28800 -> 36000)
        migrations.AlterField(
            model_name='report',
            name='daily_norm_sec',
            field=models.IntegerField(default=36000, verbose_name='Норма работы в смену (сек)'),
        ),

        # 6. VehicleRecord: add mileage
        migrations.AddField(
            model_name='vehiclerecord',
            name='mileage',
            field=models.FloatField(blank=True, null=True, verbose_name='Пробег (км)'),
        ),

        # 7. VehicleRecord: add refueling
        migrations.AddField(
            model_name='vehiclerecord',
            name='refueling',
            field=models.FloatField(blank=True, null=True, verbose_name='Объём заправок (л)'),
        ),

        # 8. VehicleRecord: add comment
        migrations.AddField(
            model_name='vehiclerecord',
            name='comment',
            field=models.TextField(blank=True, default='', verbose_name='Комментарий'),
        ),

        # 9. VehicleRecord: add record_date
        migrations.AddField(
            model_name='vehiclerecord',
            name='record_date',
            field=models.DateField(blank=True, null=True, verbose_name='Дата (полная)'),
        ),

        # 10. VehicleRecord: engine_time_sec set default=0 (was no default)
        migrations.AlterField(
            model_name='vehiclerecord',
            name='engine_time_sec',
            field=models.FloatField(default=0, verbose_name='Время работы двигателя (сек)'),
        ),

        # 11. VehicleRecord: engine_no_move_sec set default=0
        migrations.AlterField(
            model_name='vehiclerecord',
            name='engine_no_move_sec',
            field=models.FloatField(default=0, verbose_name='Время работы без движения (сек)'),
        ),

        # 12. VehicleRecord: engine_idle_sec set default=0
        migrations.AlterField(
            model_name='vehiclerecord',
            name='engine_idle_sec',
            field=models.FloatField(default=0, verbose_name='Время холостого хода (сек)'),
        ),

        # 13. VehicleRecord: fuel_norm set default=0
        migrations.AlterField(
            model_name='vehiclerecord',
            name='fuel_norm',
            field=models.FloatField(default=0, verbose_name='Норма расхода (л/ч)'),
        ),
    ]
