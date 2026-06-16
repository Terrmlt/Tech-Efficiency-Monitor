from django.contrib import admin
from .models import Report, VehicleRecord


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ['name', 'period', 'uploaded_at', 'daily_norm_sec']
    list_filter = ['uploaded_at']
    search_fields = ['name', 'period']


@admin.register(VehicleRecord)
class VehicleRecordAdmin(admin.ModelAdmin):
    list_display = ['name', 'group', 'date', 'has_anomaly', 'fuel_efficiency', 'equipment_output']
    list_filter = ['group', 'has_anomaly', 'report']
    search_fields = ['name']
