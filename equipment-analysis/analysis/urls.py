from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('upload/', views.upload, name='upload'),
    path('report/<int:pk>/', views.report_detail, name='report_detail'),
    path('report/<int:pk>/delete/', views.delete_report, name='delete_report'),
]
