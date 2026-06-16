from django.db import models
import json


class Report(models.Model):
    name = models.CharField(max_length=300, verbose_name='Название отчёта')
    file = models.FileField(upload_to='reports/', verbose_name='Файл Excel')
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата загрузки')
    period = models.CharField(max_length=300, blank=True, verbose_name='Период')
    vehicles_list = models.TextField(blank=True, verbose_name='Список ТС')

    daily_norm_hours = models.FloatField(default=8.0, verbose_name='Норма работы в сутки (час)')
    bulldozer_idle_norm_pct = models.FloatField(default=30.0, verbose_name='Норма холостого хода бульдозеров/погрузчиков (% от времени работы)')
    excavator_downtime_norm_pct = models.FloatField(default=30.0, verbose_name='Норма времени простоя стрелы экскаваторов (% от времени работы)')
    dumptruck_nomove_norm_pct = models.FloatField(default=40.0, verbose_name='Норма времени без движения самосвалов (% от времени работы)')

    class Meta:
        verbose_name = 'Отчёт'
        verbose_name_plural = 'Отчёты'
        ordering = ['-uploaded_at']

    def __str__(self):
        return self.name

    def get_anomaly_count(self):
        return self.vehiclerecord_set.filter(has_anomaly=True).count()

    def get_total_count(self):
        return self.vehiclerecord_set.count()


class VehicleRecord(models.Model):
    GROUP_BULLDOZER = 'Бульдозеры'
    GROUP_EXCAVATOR = 'Экскаваторы'
    GROUP_DUMPTRUCK = 'Самосвалы'
    GROUP_LOADER = 'Погрузчики'

    report = models.ForeignKey(Report, on_delete=models.CASCADE, verbose_name='Отчёт')
    row_number = models.IntegerField(default=0, verbose_name='№')
    name = models.CharField(max_length=200, verbose_name='Название ТС')
    group = models.CharField(max_length=100, verbose_name='Группа ТС')
    date = models.CharField(max_length=50, verbose_name='Дата')

    engine_time_sec = models.FloatField(verbose_name='Время работы двигателя (сек)')
    engine_no_move_sec = models.FloatField(verbose_name='Время работы без движения (сек)')
    engine_idle_sec = models.FloatField(verbose_name='Время холостого хода (сек)')
    fuel_norm = models.FloatField(verbose_name='Норма расхода (л/ч)')
    fuel_actual = models.FloatField(null=True, blank=True, verbose_name='Фактический расход (л)')
    downtime_sec = models.FloatField(null=True, blank=True, verbose_name='Время простоя (сек)')

    has_anomaly = models.BooleanField(default=False, verbose_name='Есть аномалия')
    anomaly_details = models.JSONField(default=list, verbose_name='Описание аномалий')

    fuel_efficiency = models.FloatField(null=True, blank=True, verbose_name='Расход к норме')
    equipment_output = models.FloatField(null=True, blank=True, verbose_name='Выход техники')
    type_efficiency = models.FloatField(null=True, blank=True, verbose_name='Эффективность (тип)')

    class Meta:
        verbose_name = 'Запись по ТС'
        verbose_name_plural = 'Записи по ТС'
        ordering = ['row_number']

    def __str__(self):
        return f'{self.name} ({self.date})'

    def engine_time_hours(self):
        return self.engine_time_sec / 3600

    def engine_no_move_hours(self):
        return self.engine_no_move_sec / 3600

    def engine_idle_hours(self):
        return self.engine_idle_sec / 3600

    def downtime_hours(self):
        if self.downtime_sec is not None:
            return self.downtime_sec / 3600
        return None

    def format_duration(self, seconds):
        if seconds is None:
            return '—'
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f'{h:02d}:{m:02d}:{s:02d}'

    def engine_time_str(self):
        return self.format_duration(self.engine_time_sec)

    def engine_no_move_str(self):
        return self.format_duration(self.engine_no_move_sec)

    def engine_idle_str(self):
        return self.format_duration(self.engine_idle_sec)

    def downtime_str(self):
        return self.format_duration(self.downtime_sec)

    def fuel_efficiency_pct(self):
        if self.fuel_efficiency is not None:
            return round(self.fuel_efficiency * 100, 1)
        return None

    def equipment_output_pct(self):
        if self.equipment_output is not None:
            return round(self.equipment_output * 100, 1)
        return None

    def type_efficiency_pct(self):
        if self.type_efficiency is not None:
            return round(self.type_efficiency, 1)
        return None

    def is_bulldozer_or_loader(self):
        return self.group in [self.GROUP_BULLDOZER, self.GROUP_LOADER]

    def is_excavator(self):
        return self.group == self.GROUP_EXCAVATOR

    def is_dumptruck(self):
        return self.group == self.GROUP_DUMPTRUCK
