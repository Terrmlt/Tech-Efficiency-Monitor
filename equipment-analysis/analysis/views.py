from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction

from .forms import ReportUploadForm
from .models import Report, VehicleRecord
from .utils import parse_excel_file, detect_anomalies, calculate_metrics, build_summary


def index(request):
    reports = Report.objects.all()
    return render(request, 'analysis/index.html', {'reports': reports})


def upload(request):
    if request.method == 'POST':
        form = ReportUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    report = form.save()
                    metadata, records_data = parse_excel_file(report.file.path)

                    if metadata.get('period'):
                        report.period = metadata['period']
                    if metadata.get('vehicles_list'):
                        report.vehicles_list = metadata['vehicles_list']
                    if metadata.get('report_name') and not report.name:
                        report.name = metadata['report_name']
                    report.save()

                    for rec_data in records_data:
                        has_anomaly, anomaly_details = detect_anomalies(rec_data)
                        metrics = calculate_metrics(rec_data, report)

                        VehicleRecord.objects.create(
                            report=report,
                            row_number=rec_data['row_number'],
                            name=rec_data['name'],
                            group=rec_data['group'],
                            date=rec_data['date'],
                            engine_time_sec=rec_data['engine_time_sec'],
                            engine_no_move_sec=rec_data['engine_no_move_sec'],
                            engine_idle_sec=rec_data['engine_idle_sec'],
                            fuel_norm=rec_data['fuel_norm'],
                            fuel_actual=rec_data['fuel_actual'],
                            downtime_sec=rec_data['downtime_sec'],
                            has_anomaly=has_anomaly,
                            anomaly_details=anomaly_details,
                            fuel_efficiency=metrics['fuel_efficiency'],
                            equipment_output=metrics['equipment_output'],
                            type_efficiency=metrics['type_efficiency'],
                        )

                messages.success(request, f'Отчёт успешно загружен: {report.vehiclerecord_set.count()} записей.')
                return redirect('report_detail', pk=report.pk)

            except Exception as e:
                messages.error(request, f'Ошибка при обработке файла: {str(e)}')
                if 'report' in locals() and report.pk:
                    report.delete()
    else:
        form = ReportUploadForm()

    return render(request, 'analysis/upload.html', {'form': form})


def report_detail(request, pk):
    report = get_object_or_404(Report, pk=pk)
    records = report.vehiclerecord_set.all()

    group_filter = request.GET.get('group', '')
    anomaly_filter = request.GET.get('anomaly', '')

    if group_filter:
        records = records.filter(group=group_filter)
    if anomaly_filter == 'yes':
        records = records.filter(has_anomaly=True)
    elif anomaly_filter == 'no':
        records = records.filter(has_anomaly=False)

    all_records = report.vehiclerecord_set.all()
    summary = build_summary(all_records, report)
    groups = all_records.values_list('group', flat=True).distinct().order_by('group')

    context = {
        'report': report,
        'records': records,
        'summary': summary,
        'groups': groups,
        'group_filter': group_filter,
        'anomaly_filter': anomaly_filter,
        'total_count': all_records.count(),
        'anomaly_count': all_records.filter(has_anomaly=True).count(),
    }
    return render(request, 'analysis/report_detail.html', context)


def delete_report(request, pk):
    report = get_object_or_404(Report, pk=pk)
    if request.method == 'POST':
        name = report.name
        report.delete()
        messages.success(request, f'Отчёт «{name}» удалён.')
    return redirect('index')
