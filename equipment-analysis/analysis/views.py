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
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    from collections import defaultdict

    report = get_object_or_404(Report, pk=pk)
    all_records = list(report.vehiclerecord_set.all().order_by('group', 'row_number'))
    summary = build_summary(all_records, report)

    wb = openpyxl.Workbook()

    # ── Цвета ──────────────────────────────────────────────────────────
    DARK_BLUE  = '1F3864'
    MID_BLUE   = '2E75B6'
    YELLOW_BG  = 'FFF2CC'
    ORANGE_BG  = 'FCE4D6'
    GREEN_BG   = 'E2EFDA'
    RED_BG     = 'FFE0E0'
    GREY_BG    = 'F2F2F2'
    GROUP_BG   = 'D6E4F0'
    TOTAL_BG   = 'BDD7EE'
    GRAND_BG   = '1F3864'

    def make_font(bold=False, color='000000', size=10, name='Calibri'):
        return Font(bold=bold, color=color, size=size, name=name)

    def make_fill(color):
        return PatternFill('solid', fgColor=color)

    def make_align(h='center', v='center', wrap=False):
        return Alignment(horizontal=h, vertical=v, wrap_text=wrap)

    def thin_border():
        s = Side(style='thin', color='BFBFBF')
        return Border(left=s, right=s, top=s, bottom=s)

    def pct_fill(val, good_max, warn_max, invert=False):
        if val is None:
            return None
        ok  = val <= good_max if not invert else val >= good_max
        mid = val <= warn_max if not invert else val >= warn_max
        if ok:   return make_fill(GREEN_BG)
        if mid:  return make_fill(YELLOW_BG)
        return make_fill(ORANGE_BG)

    NCOLS = 12

    # ══════════════════════════════════════════════════════════════════
    # Лист 1 — Детализация + итоги
    # ══════════════════════════════════════════════════════════════════
    ws = wb.active
    ws.title = 'Отчёт'

    def write_merged(row_num, text, bg, fg='FFFFFF', bold=True, size=11):
        ws.merge_cells(f'A{row_num}:{get_column_letter(NCOLS)}{row_num}')
        c = ws.cell(row=row_num, column=1)
        c.value = text
        c.font = Font(bold=bold, color=fg, size=size, name='Calibri')
        c.fill = make_fill(bg)
        c.alignment = make_align('center')
        ws.row_dimensions[row_num].height = 22

    # Строка 1 — заголовок отчёта
    write_merged(1, f'Анализ эффективности техники — {report.name}', DARK_BLUE, size=13)
    ws.row_dimensions[1].height = 28

    # Строка 2 — период
    period_text = f'Период: {report.period}' if report.period else ''
    write_merged(2, period_text, 'E8F0FB', '595959', bold=False, size=10)

    # Строка 3 — нормативы
    ws.append([
        'Норма/сутки (ч):', report.daily_norm_hours,
        'Хол.ход бульдозеры (%):', report.bulldozer_idle_norm_pct,
        'Простой стрелы экскаваторы (%):', report.excavator_downtime_norm_pct,
        'Без движения самосвалы (%):', report.dumptruck_nomove_norm_pct,
        None, None, None, None,
    ])
    for col in range(1, NCOLS + 1):
        c = ws.cell(row=3, column=col)
        c.font = Font(bold=(col % 2 == 1), size=9, name='Calibri', color='444444')
        c.fill = make_fill(GREY_BG)
        c.alignment = make_align('center')

    ws.append([])  # пустая строка 4

    # Строка 5 — заголовки колонок
    COL_HEADERS = [
        '№', 'Техника', 'Группа', 'Дата',
        'Время работы\n(чч:мм:сс)',
        'Расход\nфакт (л)',
        'Норма расхода\n(л/ч)',
        'Расход\nк норме (%)',
        'Выход\nтехники (%)',
        'Эффективность\n(%)',
        'Тип\nэффективности',
        'Аномалии',
    ]
    ws.append(COL_HEADERS)
    HDR_ROW = 5
    for col in range(1, NCOLS + 1):
        c = ws.cell(row=HDR_ROW, column=col)
        c.font = Font(bold=True, color='FFFFFF', size=10, name='Calibri')
        c.fill = make_fill(MID_BLUE)
        c.alignment = make_align('center', wrap=True)
        c.border = thin_border()
    ws.row_dimensions[HDR_ROW].height = 36

    ws.freeze_panes = f'A{HDR_ROW + 1}'

    # ── Данные по каждой единице техники ──────────────────────────────
    # Группируем: сначала все строки по группе
    records_by_group = defaultdict(list)
    for rec in all_records:
        records_by_group[rec.group].append(rec)

    # Для группового итога накапливаем значения
    for group_name in sorted(records_by_group.keys()):
        group_records = records_by_group[group_name]

        # Заголовок группы
        ws.append([])
        gr = ws.max_row
        ws.merge_cells(f'A{gr}:{get_column_letter(NCOLS)}{gr}')
        gc = ws.cell(row=gr, column=1)
        gc.value = f'  {group_name.upper()}  ({len(group_records)} ед.)'
        gc.font = Font(bold=True, color=DARK_BLUE, size=10, name='Calibri')
        gc.fill = make_fill(GROUP_BG)
        gc.alignment = make_align('left')
        ws.row_dimensions[gr].height = 18

        # Накопители для итога группы
        g_fuel_actual_sum = 0.0
        g_engine_h_sum    = 0.0
        g_fuel_eff_vals   = []
        g_output_vals     = []
        g_type_eff_vals   = []
        g_anomaly_count   = 0

        for rec in group_records:
            fuel_eff_pct = round(rec.fuel_efficiency * 100, 1) if rec.fuel_efficiency is not None else None
            output_pct   = round(rec.equipment_output * 100, 1) if rec.equipment_output is not None else None
            type_eff_pct = round(rec.type_efficiency * 100, 1) if rec.type_efficiency is not None else None

            type_label = {
                'Бульдозеры': 'Холостой ход',
                'Погрузчики': 'Холостой ход',
                'Экскаваторы': 'Простой стрелы',
                'Самосвалы': 'Без движения',
            }.get(rec.group, '')

            anomaly_text = '; '.join(rec.anomaly_details) if rec.has_anomaly else ''

            ws.append([
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
            ])
            r = ws.max_row
            row_fill = make_fill(YELLOW_BG) if rec.has_anomaly else None

            for col in range(1, NCOLS + 1):
                c = ws.cell(row=r, column=col)
                c.font = make_font()
                c.alignment = make_align()
                c.border = thin_border()
                if row_fill and col not in (8, 9, 10):
                    c.fill = row_fill

            ws.cell(row=r, column=2).alignment = make_align('left')
            ws.cell(row=r, column=12).alignment = make_align('left', wrap=True)

            f = pct_fill(fuel_eff_pct, 100, 115)
            if f: ws.cell(row=r, column=8).fill = f
            f = pct_fill(output_pct, 90, 70, invert=True)
            if f: ws.cell(row=r, column=9).fill = f
            f = pct_fill(type_eff_pct, 100, 130)
            if f: ws.cell(row=r, column=10).fill = f

            if rec.fuel_actual is not None and rec.fuel_actual < 0:
                ws.cell(row=r, column=6).fill = make_fill('FFB3B3')
                ws.cell(row=r, column=6).font = Font(bold=True, color='C00000', name='Calibri', size=10)

            # Накопление
            if rec.fuel_actual and rec.fuel_actual > 0:
                g_fuel_actual_sum += rec.fuel_actual
            g_engine_h_sum += rec.engine_time_sec / 3600
            if fuel_eff_pct is not None: g_fuel_eff_vals.append(fuel_eff_pct)
            if output_pct   is not None: g_output_vals.append(output_pct)
            if type_eff_pct is not None: g_type_eff_vals.append(type_eff_pct)
            if rec.has_anomaly: g_anomaly_count += 1

        # Итог по группе
        g_avg_fuel = round(sum(g_fuel_eff_vals) / len(g_fuel_eff_vals), 1) if g_fuel_eff_vals else None
        g_avg_out  = round(sum(g_output_vals)   / len(g_output_vals),   1) if g_output_vals  else None
        g_avg_type = round(sum(g_type_eff_vals) / len(g_type_eff_vals), 1) if g_type_eff_vals else None

        ws.append([
            '', f'ИТОГО {group_name}',
            '', '',
            f'{round(g_engine_h_sum, 1)} ч',
            round(g_fuel_actual_sum, 1),
            '',
            g_avg_fuel,
            g_avg_out,
            g_avg_type,
            '',
            f'Аномалий: {g_anomaly_count}' if g_anomaly_count else '',
        ])
        tr = ws.max_row
        for col in range(1, NCOLS + 1):
            c = ws.cell(row=tr, column=col)
            c.font = Font(bold=True, size=10, name='Calibri', color=DARK_BLUE)
            c.fill = make_fill(TOTAL_BG)
            c.alignment = make_align('center')
            c.border = thin_border()
        ws.cell(row=tr, column=2).alignment = make_align('left')
        ws.row_dimensions[tr].height = 18

        f = pct_fill(g_avg_fuel, 100, 115)
        if f: ws.cell(row=tr, column=8).fill = f
        f = pct_fill(g_avg_out, 90, 70, invert=True)
        if f: ws.cell(row=tr, column=9).fill = f
        f = pct_fill(g_avg_type, 100, 130)
        if f: ws.cell(row=tr, column=10).fill = f

        if g_anomaly_count:
            ws.cell(row=tr, column=12).fill = make_fill(ORANGE_BG)

    # ── Общий итог ────────────────────────────────────────────────────
    ws.append([])

    # Заголовок «ОБЩИЙ ИТОГ»
    oi_hdr_row = ws.max_row + 1
    ws.append([])
    ws.merge_cells(f'A{oi_hdr_row}:{get_column_letter(NCOLS)}{oi_hdr_row}')
    c = ws.cell(row=oi_hdr_row, column=1)
    c.value = 'ОБЩИЙ ИТОГ ПО ВСЕМ ГРУППАМ'
    c.font = Font(bold=True, color='FFFFFF', size=11, name='Calibri')
    c.fill = make_fill(GRAND_BG)
    c.alignment = make_align('center')
    ws.row_dimensions[oi_hdr_row].height = 22

    # Заголовки сводной таблицы
    summary_col_headers = [
        'Группа ТС', 'Кол-во ед.', 'Аномалий',
        'Всего часов', 'Расход (л)',
        'Расход к норме (%)', 'Выход техники (%)', 'Эффективность (%)',
        'Тип эффективности', None, None, None,
    ]
    ws.append(summary_col_headers)
    sh_row = ws.max_row
    for col in range(1, 10):
        c = ws.cell(row=sh_row, column=col)
        c.font = Font(bold=True, color='FFFFFF', size=10, name='Calibri')
        c.fill = make_fill(MID_BLUE)
        c.alignment = make_align('center', wrap=True)
        c.border = thin_border()
    ws.row_dimensions[sh_row].height = 30

    total_units = 0
    total_anomalies = 0
    total_engine_h = 0.0
    total_fuel = 0.0

    for s in summary:
        ws.append([
            s['group'],
            s['count'],
            s['anomaly_count'],
            s['total_engine_hours'],
            s['total_fuel_actual'],
            s['avg_fuel_eff'],
            s['avg_output'],
            s['avg_type_eff'],
            s['type_eff_label'],
            None, None, None,
        ])
        sr = ws.max_row
        for col in range(1, 10):
            c = ws.cell(row=sr, column=col)
            c.font = make_font(size=10)
            c.alignment = make_align('center')
            c.border = thin_border()
        ws.cell(row=sr, column=1).alignment = make_align('left')
        ws.cell(row=sr, column=9).alignment = make_align('left')

        if s['anomaly_count']:
            ws.cell(row=sr, column=3).fill = make_fill(ORANGE_BG)

        f = pct_fill(s['avg_fuel_eff'], 100, 115)
        if f: ws.cell(row=sr, column=6).fill = f
        f = pct_fill(s['avg_output'], 90, 70, invert=True)
        if f: ws.cell(row=sr, column=7).fill = f
        f = pct_fill(s['avg_type_eff'], 100, 130)
        if f: ws.cell(row=sr, column=8).fill = f

        total_units     += s['count']
        total_anomalies += s['anomaly_count']
        total_engine_h  += s['total_engine_hours']
        total_fuel      += s['total_fuel_actual']

    # Строка «Всего»
    ws.append([
        'ВСЕГО',
        total_units,
        total_anomalies,
        round(total_engine_h, 1),
        round(total_fuel, 1),
        None, None, None, None, None, None, None,
    ])
    grand_row = ws.max_row
    for col in range(1, 10):
        c = ws.cell(row=grand_row, column=col)
        c.font = Font(bold=True, color='FFFFFF', size=10, name='Calibri')
        c.fill = make_fill(DARK_BLUE)
        c.alignment = make_align('center')
        c.border = thin_border()
    ws.cell(row=grand_row, column=1).alignment = make_align('left')
    ws.row_dimensions[grand_row].height = 20

    # ── Ширины колонок ────────────────────────────────────────────────
    col_widths = [5, 30, 14, 12, 16, 14, 13, 13, 13, 14, 16, 45]
    for i, w in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    # ══════════════════════════════════════════════════════════════════
    # Лист 2 — Аномалии (если есть)
    # ══════════════════════════════════════════════════════════════════
    anomaly_records = [r for r in all_records if r.has_anomaly]
    if anomaly_records:
        ws_a = wb.create_sheet('Аномалии')

        ws_a.merge_cells(f'A1:E1')
        c = ws_a['A1']
        c.value = f'Аномальные записи — {report.name}'
        c.font = Font(bold=True, color='FFFFFF', size=12, name='Calibri')
        c.fill = make_fill('C00000')
        c.alignment = make_align('center')
        ws_a.row_dimensions[1].height = 24

        for col, txt in enumerate(['№', 'Техника', 'Группа', 'Дата', 'Описание аномалии'], 1):
            c = ws_a.cell(row=2, column=col)
            c.value = txt
            c.font = Font(bold=True, color='FFFFFF', size=10, name='Calibri')
            c.fill = make_fill('9B2335')
            c.alignment = make_align('center')
            c.border = thin_border()
        ws_a.row_dimensions[2].height = 24

        for rec in anomaly_records:
            for anomaly_text in rec.anomaly_details:
                ws_a.append([rec.row_number, rec.name, rec.group, rec.date, anomaly_text])
                r = ws_a.max_row
                for col in range(1, 6):
                    c = ws_a.cell(row=r, column=col)
                    c.font = make_font()
                    c.alignment = make_align()
                    c.border = thin_border()
                    c.fill = make_fill(RED_BG)
                ws_a.cell(row=r, column=2).alignment = make_align('left')
                ws_a.cell(row=r, column=5).alignment = make_align('left', wrap=True)

        for i, w in enumerate([5, 30, 14, 12, 60], 1):
            ws_a.column_dimensions[get_column_letter(i)].width = w

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
