from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('upload/', views.upload, name='upload'),
    path('report/<int:pk>/', views.report_detail, name='report_detail'),
    path('report/<int:pk>/delete/', views.delete_report, name='delete_report'),
    path('report/<int:pk>/export/', views.export_excel, name='export_excel'),
    path('report/<int:pk>/vehicle-norms/', views.set_vehicle_norms, name='set_vehicle_norms'),
    path('report/<int:pk>/vehicle-norm/save/', views.save_vehicle_norm, name='save_vehicle_norm'),
    path('records/', views.records, name='records'),
    path('records/export/', views.export_records_excel, name='export_records_excel'),
    path('analytics/', views.analytics, name='analytics'),
    path('records/<int:pk>/comment/', views.save_comment, name='save_comment'),
    path('sections/', views.sections, name='sections'),
    path('sections/new/', views.section_create, name='section_create'),
    path('sections/<int:pk>/edit/', views.section_edit, name='section_edit'),
    path('sections/<int:pk>/delete/', views.section_delete, name='section_delete'),
]
