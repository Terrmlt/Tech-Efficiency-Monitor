from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('upload/', views.upload, name='upload'),
    path('report/<int:pk>/', views.report_detail, name='report_detail'),
    path('report/<int:pk>/delete/', views.delete_report, name='delete_report'),
    path('report/<int:pk>/export/', views.export_excel, name='export_excel'),
    path('report/<int:pk>/vehicle-norms/', views.set_vehicle_norms, name='set_vehicle_norms'),
    path('records/', views.records, name='records'),
    path('records/export/', views.export_records_excel, name='export_records_excel'),
    path('analytics/', views.analytics, name='analytics'),
    path('analytics/compare/', views.analytics_compare, name='analytics_compare'),
    path('analytics/efficiency/', views.analytics_efficiency, name='analytics_efficiency'),
    path('records/<int:pk>/comment/', views.save_comment, name='save_comment'),
    path('sections/', views.sections, name='sections'),
    path('sections/new/', views.section_create, name='section_create'),
    path('sections/<int:pk>/edit/', views.section_edit, name='section_edit'),
    path('sections/<int:pk>/delete/', views.section_delete, name='section_delete'),

    path('users/', views.users_list, name='users_list'),
    path('users/new/', views.user_create, name='user_create'),
    path('users/<int:pk>/edit/', views.user_edit, name='user_edit'),
    path('users/<int:pk>/delete/', views.user_delete, name='user_delete'),
    path('users/<int:pk>/set-section/', views.user_set_section, name='user_set_section'),

    # ── Мониторинг Омникомм ──────────────────────────────────────────────────
    path('monitoring/', views.monitoring_index, name='monitoring_index'),
    path('monitoring/test-email/', views.monitoring_send_test_email, name='monitoring_test_email'),
    path('monitoring/settings/', views.monitoring_smtp_settings, name='monitoring_smtp_settings'),
    path('monitoring/group/<str:group>/', views.monitoring_group, name='monitoring_group'),
    path('monitoring/group/<str:group>/save/', views.monitoring_save, name='monitoring_save'),
    path('monitoring/analytics/', views.monitoring_analytics, name='monitoring_analytics'),
    path('monitoring/analytics/drill/', views.monitoring_fault_drill, name='monitoring_fault_drill'),

    # Reference: vehicles
    path('monitoring/vehicles/', views.monitoring_vehicles, name='monitoring_vehicles'),
    path('monitoring/vehicles/import/', views.monitoring_vehicle_import, name='monitoring_vehicle_import'),
    path('monitoring/vehicles/new/', views.monitoring_vehicle_create, name='monitoring_vehicle_create'),
    path('monitoring/vehicles/<int:pk>/edit/', views.monitoring_vehicle_edit, name='monitoring_vehicle_edit'),
    path('monitoring/vehicles/<int:pk>/delete/', views.monitoring_vehicle_delete, name='monitoring_vehicle_delete'),

    # Reference: breakdown types
    path('monitoring/breakdowns/', views.monitoring_breakdowns, name='monitoring_breakdowns'),
    path('monitoring/breakdowns/new/', views.monitoring_breakdown_create, name='monitoring_breakdown_create'),
    path('monitoring/breakdowns/<int:pk>/edit/', views.monitoring_breakdown_edit, name='monitoring_breakdown_edit'),
    path('monitoring/breakdowns/<int:pk>/delete/', views.monitoring_breakdown_delete, name='monitoring_breakdown_delete'),

    # Reference: failure causes
    path('monitoring/failures/', views.monitoring_failures, name='monitoring_failures'),
    path('monitoring/failures/new/', views.monitoring_failure_create, name='monitoring_failure_create'),
    path('monitoring/failures/<int:pk>/edit/', views.monitoring_failure_edit, name='monitoring_failure_edit'),
    path('monitoring/failures/<int:pk>/delete/', views.monitoring_failure_delete, name='monitoring_failure_delete'),
]
