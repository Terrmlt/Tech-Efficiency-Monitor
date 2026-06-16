import io
import re
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse

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


def export_excel(request, pk):
    import openpyxl
    from openpyxl.styles import (
        Font, PatternFill, Alignment, Border, Side, numbers
    )
    from openpyxl.utils import get_column_letter

    report = get_object_or_404(Report, pk=pk)
    all_records = report.vehiclerecord_set.all()
    summary = build_summary(all_records, report)

    wb = openpyxl.Workbook()

    # ── Стили ──────────────────────────────────────────────────────────
    DARK_BLUE  = '1F3864'
    MID_BLUE   = '2E75B6'
    LIGHT_BLUE = 'DEEAF1'
    YELLOW_BG  = 'FFF2CC'
    ORANGE_BG  = 'FCE4D6'
    GREEN_BG   = 'E2EFDA'
    RED_BG     = 'FFE0E0'
    GREY_BG    = 'F2F2F2'

    def hdr(text, bg=DARK_BLUE, fg='FFFFFF', bold=True, size=11, wrap=True, halign='center'):
        cell_font  = Font(bold=bold, color=fg, size=size, name='Calibri')
        cell_fill  = PatternFill('solid', fgColor=bg)
        cell_align = Alignment(horizontal=halign, vertical='center',
                               wrap_text=wrap)
        return cell_font, cell_fill, cell_align

    def thin_border():
        s = Side(style='thin', color='BFBFBF')
        return Border(left=s, right=s, top=s, bottom=s)

    def pct_color(val, good_max, warn_max, invert=False):
        """Return fill color based on value vs thresholds."""
        if val is None:
            return None
        if invert:
            if val >= good_max:   return PatternFill('solid', fgColor=GREEN_BG)
            if val >= warn_max:   return PatternFill('solid', fgColor=YELLOW_BG)
            return PatternFill('solid', fgColor=ORANGE_BG)
        else:
            if val <= good_max:   return PatternFill('solid', fgColor=GREEN_BG)
            if val <= warn_max:   return PatternFill('solid', fgColor=YELLOW_BG)
            return PatternFill('solid', fgColor=ORANGE_BG)

    # ── Лист 1: Сводка ────────────────────────────────────────────────
    ws_sum = wb.active
    ws_sum.title = 'Сводка'

    ws_sum.merge_cells('A1:H1')
    c = ws_sum['A1']
    c.value = f'Анализ эффективности техники — {report.name}'
    c.font, c.fill, c.alignment = hdr(c.value, DARK_BLUE, size=13)

    ws_sum.merge_cells('A2:H2')
    c = ws_sum['A2']
    c.value = f'Период: {report.period}' if report.period else ''
    c.font = Font(italic=True, color='595959', name='Calibri')
    c.alignment = Alignment(horizontal='center', vertical='center')

    ws_sum.append([])

    norm_row = [
        'Норма работы/сутки (ч):', report.daily_norm_hours,
        'Хол.ход бульдозеры (%):', report.bulldozer_idle_norm_pct,
        'Простой стрелы экскаваторы (%):', report.excavator_downtime_norm_pct,
        'Без движения самосвалы (%):', report.dumptruck_nomove_norm_pct,
    ]
    ws_sum.append(norm_row)
    for col in range(1, 9):
        c = ws_sum.cell(row=4, column=col)
        c.font = Font(bold=(col % 2 == 1), size=9, name='Calibri')
        c.fill = PatternFill('solid', fgColor=GREY_BG)
        c.alignment = Alignment(horizontal='center', vertical='center')

    ws_sum.append([])

    sum_headers = [
        'Группа ТС', 'Кол-во', 'Аномалий',
        'Всего часов', 'Расход топлива (л)',
        'Расход к норме (%)', 'Выход техники (%)', 'Эффективность (%)',
    ]
    ws_sum.append(sum_headers)
    for col, _ in enumerate(sum_headers, 1):
        c = ws_sum.cell(row=6, column=col)
        c.font, c.fill, c.alignment = hdr(c.value, MID_BLUE)
        c.border = thin_border()

    for s in summary:
        row = [
            s['group'], s['count'], s['anomaly_count'],
            s['total_engine_hours'], s['total_fuel_actual'],
            s['avg_fuel_eff'], s['avg_output'], s['avg_type_eff'],
        ]
        ws_sum.append(row)
        r = ws_sum.max_row
        for col in range(1, 9):
            c = ws_sum.cell(row=r, column=col)
            c.alignment = Alignment(horizontal='center', vertical='center')
            c.border = thin_border()
            c.font = Font(name='Calibri', size=10)
        ws_sum.cell(row=r, column=1).alignment = Alignment(horizontal='left', vertical='center')

        fill = pct_color(s['avg_fuel_eff'], 100, 115)
        if fill: ws_sum.cell(row=r, column=6).fill = fill
        fill = pct_color(s['avg_output'], 90, 70, invert=True)
        if fill: ws_sum.cell(row=r, column=7).fill = fill
        fill = pct_color(s['avg_type_eff'], 100, 130)
        if fill: ws_sum.cell(row=r, column=8).fill = fill

        anom_c = ws_sum.cell(row=r, column=3)
        if s['anomaly_count'] > 0:
            anom_c.fill = PatternFill('solid', fgColor=ORANGE_BG)

    ws_sum.column_dimensions['A'].width = 20
    for col in range(2, 9):
        ws_sum.column_dimensions[get_column_letter(col)].width = 17
    ws_sum.row_dimensions[1].height = 28
    ws_sum.row_dimensions[6].height = 32

    # ── Лист 2: Детализация ───────────────────────────────────────────
    ws = wb.create_sheet('Детализация')

    ws.merge_cells('A1:L1')
    c = ws['A1']
    c.value = f'{report.name}'
    c.font, c.fill, c.alignment = hdr(c.value, DARK_BLUE, size=12)
    ws.row_dimensions[1].height = 24

    detail_headers = [
        '№', 'Техника', 'Группа', 'Дата',
        'Время работы\n(чч:мм:сс)',
        'Расход факт (л)',
        'Норма расхода\n(л/ч)',
        'Расход\nк норме (%)',
        'Выход\nтехники (%)',
        'Эффективность\n(%)',
        'Тип эффективности',
        'Аномалии',
    ]
    ws.append(detail_headers)
    for col, _ in enumerate(detail_headers, 1):
        c = ws.cell(row=2, column=col)
        c.font, c.fill, c.alignment = hdr(c.value, MID_BLUE)
        c.border = thin_border()
    ws.row_dimensions[2].height = 36

    for rec in all_records:
        fuel_eff_pct  = round(rec.fuel_efficiency * 100, 1) if rec.fuel_efficiency is not None else None
        output_pct    = round(rec.equipment_output * 100, 1) if rec.equipment_output is not None else None
        type_eff_pct  = round(rec.type_efficiency * 100, 1) if rec.type_efficiency is not None else None

        type_label = ''
        if rec.group in ('Бульдозеры', 'Погрузчики'):
            type_label = 'Холостой ход'
        elif rec.group == 'Экскаваторы':
            type_label = 'Простой стрелы'
        elif rec.group == 'Самосвалы':
            type_label = 'Без движения'

        anomaly_text = '; '.join(rec.anomaly_details) if rec.has_anomaly else ''

        row_data = [
            rec.row_number,
            rec.name,
            rec.group,
            rec.date,
            rec.engine_time_str(),
            rec.fuel_actual,
            rec.fuel_norm,
            fuel_eff_pct,
            output_pct,
            type_eff_pct,
            type_label,
            anomaly_text,
        ]
        ws.append(row_data)
        r = ws.max_row

        row_fill = PatternFill('solid', fgColor=YELLOW_BG) if rec.has_anomaly else None

        for col in range(1, 13):
            c = ws.cell(row=r, column=col)
            c.font = Font(name='Calibri', size=10)
            c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=False)
            c.border = thin_border()
            if row_fill and col not in (8, 9, 10):
                c.fill = row_fill

        ws.cell(row=r, column=2).alignment = Alignment(horizontal='left', vertical='center')
        ws.cell(row=r, column=12).alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)

        fill = pct_color(fuel_eff_pct, 100, 115)
        if fill: ws.cell(row=r, column=8).fill = fill
        fill = pct_color(output_pct, 90, 70, invert=True)
        if fill: ws.cell(row=r, column=9).fill = fill
        fill = pct_color(type_eff_pct, 100, 130)
        if fill: ws.cell(row=r, column=10).fill = fill

        if rec.fuel_actual is not None and rec.fuel_actual < 0:
            ws.cell(row=r, column=6).fill = PatternFill('solid', fgColor='FFB3B3')
            ws.cell(row=r, column=6).font = Font(bold=True, color='C00000', name='Calibri', size=10)

    col_widths = [5, 28, 14, 12, 16, 14, 14, 12, 12, 14, 16, 40]
    for i, w in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    ws.freeze_panes = 'A3'

    # ── Лист 3: Аномалии ──────────────────────────────────────────────
    anomaly_records = all_records.filter(has_anomaly=True)
    if anomaly_records.exists():
        ws_anom = wb.create_sheet('Аномалии')

        ws_anom.merge_cells('A1:E1')
        c = ws_anom['A1']
        c.value = f'Аномальные записи — {report.name}'
        c.font, c.fill, c.alignment = hdr(c.value, 'C00000', size=12)
        ws_anom.row_dimensions[1].height = 24

        anom_headers = ['№', 'Техника', 'Группа', 'Дата', 'Описание аномалии']
        ws_anom.append(anom_headers)
        for col, _ in enumerate(anom_headers, 1):
            c = ws_anom.cell(row=2, column=col)
            c.font, c.fill, c.alignment = hdr(c.value, '9B2335')
            c.border = thin_border()
        ws_anom.row_dimensions[2].height = 28

        for rec in anomaly_records:
            for anomaly_text in rec.anomaly_details:
                ws_anom.append([
                    rec.row_number, rec.name, rec.group,
                    rec.date, anomaly_text,
                ])
                r = ws_anom.max_row
                for col in range(1, 6):
                    c = ws_anom.cell(row=r, column=col)
                    c.font = Font(name='Calibri', size=10)
                    c.alignment = Alignment(horizontal='center', vertical='center')
                    c.border = thin_border()
                    c.fill = PatternFill('solid', fgColor=RED_BG)
                ws_anom.cell(row=r, column=2).alignment = Alignment(horizontal='left', vertical='center')
                ws_anom.cell(row=r, column=5).alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)

        anom_col_widths = [5, 28, 14, 12, 55]
        for i, w in enumerate(anom_col_widths, 1):
            ws_anom.column_dimensions[get_column_letter(i)].width = w

    # ── Отдаём файл ───────────────────────────────────────────────────
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    safe_name = re.sub(r'[^\w\-]', '_', report.name)[:40]
    filename = f'analysis_{safe_name}.xlsx'

    response = HttpResponse(
        buf.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
