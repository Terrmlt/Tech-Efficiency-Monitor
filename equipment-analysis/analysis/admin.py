from django.contrib import admin
from .models import (
    Section, Report, VehicleRecord, VehicleNorm,
    BreakdownType, FailureCause, MonitoringVehicle, MonitoringRecord,
)


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ['name']
    search_fields = ['name']


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ['name', 'period', 'year', 'shift', 'section', 'uploaded_at']
    list_filter = ['year', 'shift', 'section', 'uploaded_at']
    search_fields = ['name', 'period']


@admin.register(VehicleRecord)
class VehicleRecordAdmin(admin.ModelAdmin):
    list_display = ['name', 'group', 'date', 'shift', 'report', 'has_anomaly', 'fuel_efficiency', 'equipment_output']
    list_filter = ['group', 'has_anomaly', 'shift', 'report']
    search_fields = ['name']


@admin.register(VehicleNorm)
class VehicleNormAdmin(admin.ModelAdmin):
    list_display = ['vehicle_name', 'report', 'shift', 'date', 'norm_str']
    list_filter = ['shift', 'report']
    search_fields = ['vehicle_name']


@admin.register(BreakdownType)
class BreakdownTypeAdmin(admin.ModelAdmin):
    list_display = ['name']
    search_fields = ['name']


@admin.register(FailureCause)
class FailureCauseAdmin(admin.ModelAdmin):
    list_display = ['name']
    search_fields = ['name']


@admin.register(MonitoringVehicle)
class MonitoringVehicleAdmin(admin.ModelAdmin):
    list_display = ['name', 'group', 'section', 'order', 'is_active']
    list_filter = ['group', 'is_active', 'section']
    search_fields = ['name']
    list_editable = ['order', 'is_active']


@admin.register(MonitoringRecord)
class MonitoringRecordAdmin(admin.ModelAdmin):
    list_display = [
        'vehicle', 'vehicle_group', 'date', 'author',
        'fault_count', 'breakdown_type', 'failure_cause',
    ]
    list_filter = ['date', 'vehicle__group', 'breakdown_type', 'failure_cause']
    search_fields = ['vehicle__name', 'author', 'note']
    date_hierarchy = 'date'

    @admin.display(description='Группа')
    def vehicle_group(self, obj):
        return obj.vehicle.group

    @admin.display(description='Неиспр. датчиков')
    def fault_count(self, obj):
        sensors = [obj.sensor_rpm, obj.sensor_dut, obj.sensor_gps, obj.sensor_gsm]
        for s in [obj.sensor_arrow, obj.sensor_cube_port, obj.sensor_uss]:
            if s is not None:
                sensors.append(s)
        n = sum(1 for s in sensors if not s)
        return f'{n} из {len(sensors)}' if n else '—'
