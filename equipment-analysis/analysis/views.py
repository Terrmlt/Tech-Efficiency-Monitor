import io
import re
import json
import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_POST
from django.db.models import Q, Avg, Count, Sum

from .forms import ReportUploadForm, SectionForm
from .models import Report, VehicleRecord, Section, VehicleNorm, secs_to_hhmmss
from .utils import parse_excel_file, detect_anomalies, calculate_metrics, build_summary


# ─── Index ────────────────────────────────────────────────────────────────────

def index(request):
    reports = Report.objects.select_related('section').all()
    return render(request, 'analysis/index.html', {'reports': reports})


# ─── Upload ───────────────────────────────────────────────────────────────────

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
                    if metadata.get('year'):
                        report.year = metadata['year']
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
                            record_date=rec_data.get('record_date'),
                            shift=rec_data.get('shift', 0),
                            engine_time_sec=rec_data['engine_time_sec'],
                            engine_no_move_sec=rec_data['engine_no_move_sec'],
                            engine_idle_sec=rec_data['engine_idle_sec'],
                            fuel_norm=rec_data['fuel_norm'],
                            fuel_actual=rec_data['fuel_actual'],
                            downtime_sec=rec_data['downtime_sec'],
                            mileage=rec_data.get('mileage'),
                            refueling=rec_data.get('refueling'),
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


# ─── Daily-view helper ────────────────────────────────────────────────────────

def _build_daily_view(records, report):
    """
    Groups records by (name, date).  Returns a flat list of row-dicts:
      {'type': 'record',      'obj': VehicleRecord}
      {'type': 'daily_total', ...computed display fields...}
    Total rows are inserted after each group that has >1 shift entry.
    """
    from .models import secs_to_hhmmss

    order = []
    groups = {}
    for rec in records:
        key = (rec.name, rec.date)
        if key not in groups:
            order.append(key)
            groups[key] = []
        groups[key].append(rec)

    rows = []
    for key in order:
        name, date = key
        recs = sorted(groups[key], key=lambda r: r.shift if r.shift else 99)

        for rec in recs:
            ov = 0
            if rec.group in ('Бульдозеры', 'Погрузчики') and report.bulldozer_norm_sec > 0:
                ov = (rec.engine_idle_sec or 0) - report.bulldozer_norm_sec
            elif rec.group == 'Экскаваторы' and report.excavator_norm_sec > 0 and rec.downtime_sec is not None:
                ov = rec.downtime_sec - report.excavator_norm_sec
            # Dump trucks: over_str is set later by report_detail enrichment loop (uses VehicleNorm)
            rows.append({'type': 'record', 'obj': rec, 'over_str': secs_to_hhmmss(ov) if ov > 0 else ''})

        if len(recs) > 1:
            n = len(recs)
            total_engine   = sum(r.engine_time_sec for r in recs)
            total_no_move  = sum(r.engine_no_move_sec for r in recs)
            total_idle     = sum(r.engine_idle_sec for r in recs)
            has_fuel       = any(r.fuel_actual is not None for r in recs)
            total_fuel     = sum(r.fuel_actual for r in recs if r.fuel_actual is not None) if has_fuel else None
            has_mileage    = any(r.mileage is not None for r in recs)
            total_mileage  = sum(r.mileage for r in recs if r.mileage is not None) if has_mileage else None
            has_ref        = any(r.refueling is not None for r in recs)
            total_ref      = sum(r.refueling for r in recs if r.refueling is not None) if has_ref else None
            has_dt         = any(r.downtime_sec is not None for r in recs)
            total_downtime = sum(r.downtime_sec for r in recs if r.downtime_sec is not None) if has_dt else None

            fuel_norm = recs[0].fuel_norm
            group     = recs[0].group

            daily_norm_n  = report.daily_norm_sec * n
            daily_hours_n = daily_norm_n / 3600 if daily_norm_n > 0 else 0

            fuel_eff = None
            if fuel_norm > 0 and daily_hours_n > 0 and total_fuel is not None and total_fuel >= 0:
                fuel_eff = round(total_fuel / (fuel_norm * daily_hours_n) * 100, 1)

            output = round(total_engine / daily_norm_n * 100, 1) if daily_norm_n > 0 else None

            type_eff = None
            if group in ('Бульдозеры', 'Погрузчики') and report.bulldozer_norm_sec > 0:
                type_eff = round(total_idle / (report.bulldozer_norm_sec * n) * 100, 1)
            elif group == 'Экскаваторы' and total_downtime is not None and report.excavator_norm_sec > 0:
                type_eff = round(total_downtime / (report.excavator_norm_sec * n) * 100, 1)
            # Dump truck daily_total efficiency is computed later in report_detail
            # after per-shift VehicleNorm data is loaded.

            rows.append({
                'type':                 'daily_total',
                'name':                 name,
                'date':                 date,
                'group':                group,
                'n':                    n,
                'has_anomaly':          any(r.has_anomaly for r in recs),
                'engine_time_str':      secs_to_hhmmss(total_engine),
                'engine_idle_str':      secs_to_hhmmss(total_idle),
                'engine_idle_sec':      total_idle,
                'engine_no_move_str':   secs_to_hhmmss(total_no_move),
                'engine_no_move_sec':   total_no_move,
                'downtime_str':         secs_to_hhmmss(total_downtime) if total_downtime is not None else '—',
                'downtime_sec':         total_downtime,
                'fuel_actual':          total_fuel,
                'fuel_norm':            fuel_norm,
                'mileage':              total_mileage,
                'refueling':            total_ref,
                'fuel_efficiency_pct':  fuel_eff,
                'equipment_output_pct': output,
                'type_efficiency_pct':  type_eff,
                'is_bulldozer_or_loader': group in ('Бульдозеры', 'Погрузчики'),
                'is_excavator':         group == 'Экскаваторы',
                'is_dumptruck':         group == 'Самосвалы',
            })

    return rows


# ─── Report detail ────────────────────────────────────────────────────────────

def report_detail(request, pk):
    report = get_object_or_404(Report, pk=pk)
    all_records = report.vehiclerecord_set.all()

    group_filter  = request.GET.get('group', '')
    anomaly_filter = request.GET.get('anomaly', '')
    shift_filter  = request.GET.get('shift', '')

    filtered = all_records
    if group_filter:
        filtered = filtered.filter(group=group_filter)
    if anomaly_filter == 'yes':
        filtered = filtered.filter(has_anomaly=True)
    elif anomaly_filter == 'no':
        filtered = filtered.filter(has_anomaly=False)
    if shift_filter:
        try:
            filtered = filtered.filter(shift=int(shift_filter))
        except ValueError:
            pass

    summary    = build_summary(all_records, report)
    groups     = all_records.values_list('group', flat=True).distinct().order_by('group')
    daily_view = _build_daily_view(filtered.order_by('row_number', 'shift'), report)

    # Per-vehicle-per-shift-per-date norms map for dump trucks
    # Key: (vehicle_name, shift, date)
    existing_norms = {
        (vn.vehicle_name, vn.shift, vn.date): vn
        for vn in VehicleNorm.objects.filter(report=report)
    }
    # Enrich rows with norm string, efficiency %, and overage time for all groups
    for row in daily_view:
        if row['type'] == 'record':
            rec = row['obj']
            if rec.group == 'Самосвалы':
                vn = existing_norms.get((rec.name, rec.shift, rec.date))
                if vn and vn.dumptruck_norm_sec:
                    row['dt_norm_str'] = vn.norm_str()
                    overage_sec = (rec.engine_no_move_sec or 0) - vn.dumptruck_norm_sec
                    row['over_str'] = secs_to_hhmmss(overage_sec) if overage_sec > 0 else ''
                else:
                    row['dt_norm_str'] = ''
                    row['over_str'] = ''
            elif rec.group in ('Бульдозеры', 'Погрузчики'):
                if report.bulldozer_norm_sec > 0:
                    overage_sec = (rec.engine_idle_sec or 0) - report.bulldozer_norm_sec
                    row['over_str'] = secs_to_hhmmss(overage_sec) if overage_sec > 0 else ''
                else:
                    row['over_str'] = ''
            elif rec.group == 'Экскаваторы':
                if report.excavator_norm_sec > 0 and rec.downtime_sec is not None:
                    overage_sec = rec.downtime_sec - report.excavator_norm_sec
                    row['over_str'] = secs_to_hhmmss(overage_sec) if overage_sec > 0 else ''
                else:
                    row['over_str'] = ''
        elif row['type'] == 'daily_total' and row.get('is_dumptruck'):
            row_date = row.get('date', '')
            total_norm_sec = 0
            for shift_key in [1, 2]:
                vn = existing_norms.get((row['name'], shift_key, row_date))
                if vn and vn.dumptruck_norm_sec:
                    total_norm_sec += vn.dumptruck_norm_sec
            if total_norm_sec:
                row['dt_norm_str'] = secs_to_hhmmss(total_norm_sec)
                no_move_sec = row.get('engine_no_move_sec') or 0
                row['type_efficiency_pct'] = round(no_move_sec / total_norm_sec * 100, 1)
                overage_sec = no_move_sec - total_norm_sec
                row['over_str'] = secs_to_hhmmss(overage_sec) if overage_sec > 0 else ''
            else:
                row['dt_norm_str'] = ''
                row['over_str'] = ''
        elif row['type'] == 'daily_total' and row.get('is_bulldozer_or_loader'):
            if report.bulldozer_norm_sec > 0:
                idle_sec = row.get('engine_idle_sec') or 0
                n_shifts = row.get('n', 1)
                overage_sec = idle_sec - report.bulldozer_norm_sec * n_shifts
                row['over_str'] = secs_to_hhmmss(overage_sec) if overage_sec > 0 else ''
            else:
                row['over_str'] = ''
        elif row['type'] == 'daily_total' and row.get('is_excavator'):
            if report.excavator_norm_sec > 0:
                dt_sec = row.get('downtime_sec') or 0
                n_shifts = row.get('n', 1)
                overage_sec = dt_sec - report.excavator_norm_sec * n_shifts
                row['over_str'] = secs_to_hhmmss(overage_sec) if overage_sec > 0 else ''
            else:
                row['over_str'] = ''

    context = {
        'report':         report,
        'daily_view':     daily_view,
        'summary':        summary,
        'groups':         groups,
        'group_filter':   group_filter,
        'anomaly_filter': anomaly_filter,
        'shift_filter':   shift_filter,
        'total_count':    all_records.count(),
        'anomaly_count':  all_records.filter(has_anomaly=True).count(),
        'shown_count':    filtered.count(),
    }
    return render(request, 'analysis/report_detail.html', context)


# ─── Vehicle norms (dump trucks) ──────────────────────────────────────────────

def _parse_hhmmss_to_sec(value):
    """Parse 'HH:MM:SS' or 'HH:MM' string to total seconds. Returns None on error."""
    if not value:
        return None
    parts = value.strip().split(':')
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(float(parts[2]))
        if len(parts) == 2:
            return int(parts[0]) * 3600 + int(parts[1]) * 60
    except (ValueError, IndexError):
        return None
    return None


@require_POST
def set_vehicle_norms(request, pk):
    """Save per-day per-shift dump truck norms and recalculate efficiency.

    Expects JSON body:
      {"norms": [{"vehicle_name": "...", "shift": 1, "date": "19.06", "norm_str": "06:10:00"}, ...]}
    Each (vehicle_name, shift, date) tuple gets its own norm.
    """
    report = get_object_or_404(Report, pk=pk)
    try:
        data = json.loads(request.body)
        norms_list = data.get('norms', [])
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Неверный формат данных'}, status=400)

    updated_records = 0
    errors = []

    with transaction.atomic():
        for item in norms_list:
            vehicle_name = (item.get('vehicle_name') or '').strip()
            shift = item.get('shift')  # int or None
            date_str = (item.get('date') or '').strip()
            norm_str = (item.get('norm_str') or '').strip()

            if not vehicle_name or not norm_str:
                continue

            norm_sec = _parse_hhmmss_to_sec(norm_str)
            if norm_sec is None or norm_sec <= 0:
                errors.append(f'{vehicle_name} С{shift} {date_str}: неверный формат нормы «{norm_str}»')
                continue

            # Save norm for this specific (vehicle, shift, date) combination.
            # shift=None safe path: use filter+update/create to avoid SQLite NULL uniqueness issue.
            if shift is not None:
                VehicleNorm.objects.update_or_create(
                    report=report,
                    vehicle_name=vehicle_name,
                    shift=shift,
                    date=date_str,
                    defaults={'dumptruck_norm_sec': norm_sec},
                )
            else:
                updated_count = VehicleNorm.objects.filter(
                    report=report, vehicle_name=vehicle_name,
                    shift__isnull=True, date=date_str,
                ).update(dumptruck_norm_sec=norm_sec)
                if updated_count == 0:
                    VehicleNorm.objects.create(
                        report=report, vehicle_name=vehicle_name,
                        shift=None, date=date_str, dumptruck_norm_sec=norm_sec,
                    )

            # Recalculate type_efficiency only for the matching record(s)
            rec_qs = VehicleRecord.objects.filter(
                report=report, name=vehicle_name, group='Самосвалы',
            )
            if shift is not None:
                rec_qs = rec_qs.filter(shift=shift)
            if date_str:
                rec_qs = rec_qs.filter(date=date_str)

            for rec in rec_qs:
                rec.type_efficiency = rec.engine_no_move_sec / norm_sec
                rec.save(update_fields=['type_efficiency'])
                updated_records += 1

    return JsonResponse({
        'ok': True,
        'updated': updated_records,
        'errors': errors,
    })


# ─── Delete report ────────────────────────────────────────────────────────────

def delete_report(request, pk):
    report = get_object_or_404(Report, pk=pk)
    if request.method == 'POST':
        name = report.name
        report.delete()
        messages.success(request, f'Отчёт «{name}» удалён.')
    return redirect('index')


# ─── Save comment (AJAX) ──────────────────────────────────────────────────────

@require_POST
def save_comment(request, pk):
    rec = get_object_or_404(VehicleRecord, pk=pk)
    try:
        data = json.loads(request.body)
        rec.comment = data.get('comment', '').strip()
        rec.save(update_fields=['comment'])
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)


# ─── Unified records view ─────────────────────────────────────────────────────

def _build_daily_view_records(records):
    """
    Like _build_daily_view but works across multiple reports.
    Groups by (name, date, report_id) so records from different reports
    for the same vehicle are kept separate.
    Each group's norms come from its own report object.
    Per-day per-shift dump truck norms are loaded from VehicleNorm.
    """
    from .models import secs_to_hhmmss

    # Collect all report IDs present in this queryset
    report_ids = set()
    rec_list = list(records)
    for rec in rec_list:
        report_ids.add(rec.report_id)

    # Load per-day per-shift norms for dump trucks: (report_id, vehicle_name, shift, date)
    dt_norms = {}
    for vn in VehicleNorm.objects.filter(report_id__in=report_ids):
        if vn.dumptruck_norm_sec:
            dt_norms[(vn.report_id, vn.vehicle_name, vn.shift, vn.date)] = vn.dumptruck_norm_sec

    order = []
    groups = {}
    for rec in rec_list:
        key = (rec.name, rec.date, rec.report_id)
        if key not in groups:
            order.append(key)
            groups[key] = []
        groups[key].append(rec)

    rows = []
    for key in order:
        name, date, report_id = key
        recs = sorted(groups[key], key=lambda r: r.shift if r.shift else 99)
        report = recs[0].report

        for rec in recs:
            ov = 0
            if rec.group in ('Бульдозеры', 'Погрузчики') and report.bulldozer_norm_sec > 0:
                ov = (rec.engine_idle_sec or 0) - report.bulldozer_norm_sec
            elif rec.group == 'Экскаваторы' and report.excavator_norm_sec > 0 and rec.downtime_sec is not None:
                ov = rec.downtime_sec - report.excavator_norm_sec
            elif rec.group == 'Самосвалы':
                # Use per-day per-shift VehicleNorm only — no global fallback
                vn_sec = dt_norms.get((report_id, rec.name, rec.shift, rec.date))
                if vn_sec:
                    ov = (rec.engine_no_move_sec or 0) - vn_sec
            rows.append({'type': 'record', 'obj': rec, 'over_str': secs_to_hhmmss(ov) if ov > 0 else ''})

        if len(recs) > 1:
            n = len(recs)
            total_engine   = sum(r.engine_time_sec for r in recs)
            total_no_move  = sum(r.engine_no_move_sec for r in recs)
            total_idle     = sum(r.engine_idle_sec for r in recs)
            has_fuel       = any(r.fuel_actual is not None for r in recs)
            total_fuel     = sum(r.fuel_actual for r in recs if r.fuel_actual is not None) if has_fuel else None
            has_mileage    = any(r.mileage is not None for r in recs)
            total_mileage  = sum(r.mileage for r in recs if r.mileage is not None) if has_mileage else None
            has_ref        = any(r.refueling is not None for r in recs)
            total_ref      = sum(r.refueling for r in recs if r.refueling is not None) if has_ref else None
            has_dt         = any(r.downtime_sec is not None for r in recs)
            total_downtime = sum(r.downtime_sec for r in recs if r.downtime_sec is not None) if has_dt else None

            fuel_norm = recs[0].fuel_norm
            group     = recs[0].group

            daily_norm_n  = report.daily_norm_sec * n
            daily_hours_n = daily_norm_n / 3600 if daily_norm_n > 0 else 0

            fuel_eff = None
            if fuel_norm > 0 and daily_hours_n > 0 and total_fuel is not None and total_fuel >= 0:
                fuel_eff = round(total_fuel / (fuel_norm * daily_hours_n) * 100, 1)

            output = round(total_engine / daily_norm_n * 100, 1) if daily_norm_n > 0 else None

            # For dump trucks: use per-day norms from VehicleNorm (sum of both shifts)
            dt_total_norm = 0
            if group == 'Самосвалы':
                for shift_key in [1, 2]:
                    s = dt_norms.get((report_id, name, shift_key, date))
                    if s:
                        dt_total_norm += s

            type_eff = None
            if group in ('Бульдозеры', 'Погрузчики') and report.bulldozer_norm_sec > 0:
                type_eff = round(total_idle / (report.bulldozer_norm_sec * n) * 100, 1)
            elif group == 'Экскаваторы' and total_downtime is not None and report.excavator_norm_sec > 0:
                type_eff = round(total_downtime / (report.excavator_norm_sec * n) * 100, 1)
            elif group == 'Самосвалы' and dt_total_norm > 0:
                type_eff = round(total_no_move / dt_total_norm * 100, 1)

            ov_total = 0
            if group in ('Бульдозеры', 'Погрузчики') and report.bulldozer_norm_sec > 0:
                ov_total = total_idle - report.bulldozer_norm_sec * n
            elif group == 'Экскаваторы' and total_downtime is not None and report.excavator_norm_sec > 0:
                ov_total = total_downtime - report.excavator_norm_sec * n
            elif group == 'Самосвалы' and dt_total_norm > 0:
                ov_total = total_no_move - dt_total_norm

            rows.append({
                'type':                 'daily_total',
                'name':                 name,
                'date':                 date,
                'record_date':          recs[0].record_date,
                'group':                group,
                'report':               report,
                'has_anomaly':          any(r.has_anomaly for r in recs),
                'engine_time_str':      secs_to_hhmmss(total_engine),
                'engine_idle_str':      secs_to_hhmmss(total_idle),
                'engine_idle_sec':      total_idle,
                'engine_no_move_str':   secs_to_hhmmss(total_no_move),
                'engine_no_move_sec':   total_no_move,
                'downtime_str':         secs_to_hhmmss(total_downtime) if total_downtime is not None else '—',
                'downtime_sec':         total_downtime,
                'fuel_actual':          total_fuel,
                'fuel_norm':            fuel_norm,
                'mileage':              total_mileage,
                'refueling':            total_ref,
                'fuel_efficiency_pct':  fuel_eff,
                'equipment_output_pct': output,
                'type_efficiency_pct':  type_eff,
                'over_str':             secs_to_hhmmss(ov_total) if ov_total > 0 else '',
                'is_bulldozer_or_loader': group in ('Бульдозеры', 'Погрузчики'),
                'is_excavator':         group == 'Экскаваторы',
                'is_dumptruck':         group == 'Самосвалы',
            })

    return rows


def records(request):
    qs = VehicleRecord.objects.select_related('report', 'report__section').all()

    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    section_id = request.GET.get('section', '')
    group_filter = request.GET.get('group', '')
    anomaly_filter = request.GET.get('anomaly', '')
    shift_filter = request.GET.get('shift', '')

    if date_from:
        try:
            qs = qs.filter(record_date__gte=datetime.date.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            qs = qs.filter(record_date__lte=datetime.date.fromisoformat(date_to))
        except ValueError:
            pass
    if section_id:
        qs = qs.filter(report__section_id=section_id)
    if group_filter:
        qs = qs.filter(group=group_filter)
    if anomaly_filter == 'yes':
        qs = qs.filter(has_anomaly=True)
    elif anomaly_filter == 'no':
        qs = qs.filter(has_anomaly=False)
    if shift_filter:
        try:
            qs = qs.filter(shift=int(shift_filter))
        except ValueError:
            pass

    total_count = qs.count()
    anomaly_count = qs.filter(has_anomaly=True).count()

    ordered = qs.order_by('record_date', 'name', 'report_id', 'shift', 'row_number')
    daily_view = _build_daily_view_records(ordered)

    sections = Section.objects.all()
    groups = VehicleRecord.objects.values_list('group', flat=True).distinct().order_by('group')

    context = {
        'daily_view': daily_view,
        'sections': sections,
        'groups': groups,
        'date_from': date_from,
        'date_to': date_to,
        'section_id': section_id,
        'group_filter': group_filter,
        'anomaly_filter': anomaly_filter,
        'shift_filter': shift_filter,
        'total_count': total_count,
        'anomaly_count': anomaly_count,
    }
    return render(request, 'analysis/records.html', context)


# ─── Analytics ────────────────────────────────────────────────────────────────

def analytics(request):
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    section_id = request.GET.get('section', '')

    qs = VehicleRecord.objects.select_related('report', 'report__section').all()

    if date_from:
        try:
            qs = qs.filter(record_date__gte=datetime.date.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            qs = qs.filter(record_date__lte=datetime.date.fromisoformat(date_to))
        except ValueError:
            pass
    if section_id:
        qs = qs.filter(report__section_id=section_id)

    # Group stats
    group_stats = []
    for group in VehicleRecord.objects.values_list('group', flat=True).distinct().order_by('group'):
        gqs = qs.filter(group=group)
        count = gqs.count()
        if count == 0:
            continue
        total_fuel = sum(r.fuel_actual for r in gqs if r.fuel_actual and r.fuel_actual > 0)
        total_hours = sum(r.engine_time_sec for r in gqs) / 3600
        fuel_eff_vals = [r.fuel_efficiency * 100 for r in gqs if r.fuel_efficiency is not None]
        output_vals = [r.equipment_output * 100 for r in gqs if r.equipment_output is not None]
        type_eff_vals = [r.type_efficiency * 100 for r in gqs if r.type_efficiency is not None]
        anomaly_count = gqs.filter(has_anomaly=True).count()

        group_stats.append({
            'group': group,
            'count': count,
            'total_fuel': round(total_fuel, 1),
            'total_hours': round(total_hours, 1),
            'avg_fuel_eff': round(sum(fuel_eff_vals) / len(fuel_eff_vals), 1) if fuel_eff_vals else None,
            'avg_output': round(sum(output_vals) / len(output_vals), 1) if output_vals else None,
            'avg_type_eff': round(sum(type_eff_vals) / len(type_eff_vals), 1) if type_eff_vals else None,
            'anomaly_count': anomaly_count,
        })

    # Daily output trend (for chart)
    from collections import defaultdict
    daily = defaultdict(lambda: {'engine_sec': 0, 'fuel': 0, 'count': 0, 'anomalies': 0})
    for rec in qs:
        if rec.record_date:
            key = rec.record_date.isoformat()
            daily[key]['engine_sec'] += rec.engine_time_sec
            if rec.fuel_actual and rec.fuel_actual > 0:
                daily[key]['fuel'] += rec.fuel_actual
            daily[key]['count'] += 1
            if rec.has_anomaly:
                daily[key]['anomalies'] += 1

    daily_labels = sorted(daily.keys())
    daily_fuel = [round(daily[d]['fuel'], 1) for d in daily_labels]
    daily_anomalies = [daily[d]['anomalies'] for d in daily_labels]

    # Total stats
    total_count = qs.count()
    total_fuel = sum(r.fuel_actual for r in qs if r.fuel_actual and r.fuel_actual > 0)
    total_hours = sum(r.engine_time_sec for r in qs) / 3600
    total_anomalies = qs.filter(has_anomaly=True).count()

    sections = Section.objects.all()

    context = {
        'group_stats': group_stats,
        'daily_labels': json.dumps(daily_labels),
        'daily_fuel': json.dumps(daily_fuel),
        'daily_anomalies': json.dumps(daily_anomalies),
        'total_count': total_count,
        'total_fuel': round(total_fuel, 1),
        'total_hours': round(total_hours, 1),
        'total_anomalies': total_anomalies,
        'sections': sections,
        'date_from': date_from,
        'date_to': date_to,
        'section_id': section_id,
    }
    return render(request, 'analysis/analytics.html', context)


# ─── Analytics Compare ────────────────────────────────────────────────────────

def analytics_compare(request):
    selected_ids = request.GET.getlist('sections')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    all_sections = list(Section.objects.all())
    comparison_data = []

    if selected_ids:
        from collections import defaultdict as _dd
        for section in all_sections:
            if str(section.pk) not in selected_ids:
                continue

            qs = VehicleRecord.objects.select_related('report').filter(report__section=section)
            if date_from:
                try:
                    qs = qs.filter(record_date__gte=datetime.date.fromisoformat(date_from))
                except ValueError:
                    pass
            if date_to:
                try:
                    qs = qs.filter(record_date__lte=datetime.date.fromisoformat(date_to))
                except ValueError:
                    pass

            recs = list(qs)
            count = len(recs)
            total_fuel = round(sum(r.fuel_actual for r in recs if r.fuel_actual and r.fuel_actual > 0), 1)
            total_hours = round(sum(r.engine_time_sec for r in recs) / 3600, 1)
            fuel_eff_vals = [r.fuel_efficiency * 100 for r in recs if r.fuel_efficiency is not None]
            output_vals   = [r.equipment_output * 100 for r in recs if r.equipment_output is not None]
            type_eff_vals = [r.type_efficiency  * 100 for r in recs if r.type_efficiency  is not None]
            anomaly_count = sum(1 for r in recs if r.has_anomaly)

            groups_map = _dd(list)
            for rec in recs:
                groups_map[rec.group].append(rec)
            group_stats = []
            for grp in sorted(groups_map):
                g = groups_map[grp]
                gfe = [r.fuel_efficiency * 100 for r in g if r.fuel_efficiency is not None]
                go  = [r.equipment_output * 100 for r in g if r.equipment_output is not None]
                gte = [r.type_efficiency  * 100 for r in g if r.type_efficiency  is not None]
                group_stats.append({
                    'group':        grp,
                    'count':        len(g),
                    'avg_fuel_eff': round(sum(gfe)/len(gfe), 1) if gfe else None,
                    'avg_output':   round(sum(go)/len(go), 1)   if go  else None,
                    'avg_type_eff': round(sum(gte)/len(gte), 1) if gte else None,
                })

            comparison_data.append({
                'section':       section,
                'count':         count,
                'total_fuel':    total_fuel,
                'total_hours':   total_hours,
                'avg_fuel_eff':  round(sum(fuel_eff_vals)/len(fuel_eff_vals), 1) if fuel_eff_vals else None,
                'avg_output':    round(sum(output_vals)/len(output_vals), 1)     if output_vals  else None,
                'avg_type_eff':  round(sum(type_eff_vals)/len(type_eff_vals), 1) if type_eff_vals else None,
                'anomaly_count': anomaly_count,
                'anomaly_pct':   round(anomaly_count / count * 100, 1) if count > 0 else 0,
                'group_stats':   group_stats,
            })

    PALETTE = ['#0d6efd','#198754','#fd7e14','#6f42c1','#dc3545','#0dcaf0','#ffc107','#20c997']
    for i, d in enumerate(comparison_data):
        d['color'] = PALETTE[i % len(PALETTE)]

    compare_json = json.dumps([
        {
            'name':         d['section'].name,
            'color':        d['color'],
            'total_hours':  d['total_hours'],
            'total_fuel':   d['total_fuel'],
            'avg_fuel_eff': d['avg_fuel_eff'],
            'avg_output':   d['avg_output'],
            'avg_type_eff': d['avg_type_eff'],
            'anomaly_pct':  d['anomaly_pct'],
        }
        for d in comparison_data
    ]) if comparison_data else '[]'

    context = {
        'all_sections':    all_sections,
        'selected_ids':    selected_ids,
        'comparison_data': comparison_data,
        'date_from':       date_from,
        'date_to':         date_to,
        'compare_json':    compare_json,
    }
    return render(request, 'analysis/compare.html', context)


# ─── Sections CRUD ────────────────────────────────────────────────────────────

def sections(request):
    all_sections = Section.objects.annotate(report_count=Count('report'))
    return render(request, 'analysis/sections.html', {'sections': all_sections})


def section_create(request):
    form = SectionForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Участок добавлен.')
        return redirect('sections')
    return render(request, 'analysis/section_form.html', {'form': form, 'title': 'Добавить участок'})


def section_edit(request, pk):
    section = get_object_or_404(Section, pk=pk)
    form = SectionForm(request.POST or None, instance=section)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Участок обновлён.')
        return redirect('sections')
    return render(request, 'analysis/section_form.html', {'form': form, 'title': 'Изменить участок'})


def section_delete(request, pk):
    section = get_object_or_404(Section, pk=pk)
    if request.method == 'POST':
        section.delete()
        messages.success(request, 'Участок удалён.')
        return redirect('sections')
    return render(request, 'analysis/section_confirm_delete.html', {'section': section})


# ─── Export Excel ─────────────────────────────────────────────────────────────

def export_excel(request, pk):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    from collections import defaultdict

    report = get_object_or_404(Report, pk=pk)
    all_records = list(report.vehiclerecord_set.all().order_by('group', 'row_number'))
    summary = build_summary(all_records, report)

    wb = _build_excel_workbook(report, all_records, summary)

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


def export_records_excel(request):
    """Export filtered records from the unified view."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    qs = VehicleRecord.objects.select_related('report', 'report__section').all()

    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    section_id = request.GET.get('section', '')
    group_filter = request.GET.get('group', '')
    anomaly_filter = request.GET.get('anomaly', '')
    shift_filter = request.GET.get('shift', '')

    if date_from:
        try:
            qs = qs.filter(record_date__gte=datetime.date.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            qs = qs.filter(record_date__lte=datetime.date.fromisoformat(date_to))
        except ValueError:
            pass
    if section_id:
        qs = qs.filter(report__section_id=section_id)
    if group_filter:
        qs = qs.filter(group=group_filter)
    if anomaly_filter == 'yes':
        qs = qs.filter(has_anomaly=True)
    elif anomaly_filter == 'no':
        qs = qs.filter(has_anomaly=False)
    if shift_filter:
        try:
            qs = qs.filter(shift=int(shift_filter))
        except ValueError:
            pass

    all_records = list(qs.order_by('record_date', 'shift', 'group', 'name'))

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Записи'

    DARK_BLUE = '1F3864'
    MID_BLUE = '2E75B6'

    def hdr_cell(ws, row, col, val):
        c = ws.cell(row=row, column=col, value=val)
        c.font = Font(bold=True, color='FFFFFF', size=10, name='Calibri')
        c.fill = PatternFill('solid', fgColor=MID_BLUE)
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        s = Side(style='thin', color='BFBFBF')
        c.border = Border(left=s, right=s, top=s, bottom=s)

    headers = [
        'Дата', 'Смена', 'Участок', 'Отчёт', '№', 'Техника', 'Группа',
        'Время работы', 'Факт. расход, л', 'Норма л/ч',
        'Расход к норме, %', 'Выход техники, %', 'Эффективность, %',
        'Простой свыше нормы',
        'Пробег, км', 'Заправка, л', 'Аномалии', 'Комментарий',
    ]
    for i, h in enumerate(headers, 1):
        hdr_cell(ws, 1, i, h)
    ws.row_dimensions[1].height = 36

    from .models import secs_to_hhmmss as _s2h

    YELLOW_BG = 'FFF2CC'
    for row_idx, rec in enumerate(all_records, 2):
        fuel_eff_pct = round(rec.fuel_efficiency * 100, 1) if rec.fuel_efficiency is not None else None
        output_pct = round(rec.equipment_output * 100, 1) if rec.equipment_output is not None else None
        type_eff_pct = round(rec.type_efficiency * 100, 1) if rec.type_efficiency is not None else None

        # Compute overage (time beyond norm)
        ov = 0
        rpt = rec.report
        if rec.group in ('Бульдозеры', 'Погрузчики') and rpt.bulldozer_norm_sec > 0:
            ov = (rec.engine_idle_sec or 0) - rpt.bulldozer_norm_sec
        elif rec.group == 'Экскаваторы' and rpt.excavator_norm_sec > 0 and rec.downtime_sec is not None:
            ov = rec.downtime_sec - rpt.excavator_norm_sec
        elif rec.group == 'Самосвалы':
            vn_sec = export_dt_norms.get((rpt.pk, rec.name, rec.shift, rec.date))
            if vn_sec:
                ov = (rec.engine_no_move_sec or 0) - vn_sec
        over_str = _s2h(ov) if ov > 0 else ''

        section_name = rec.report.section.name if rec.report.section else ''
        date_display = rec.record_date.strftime('%d.%m.%Y') if rec.record_date else rec.date

        row_data = [
            date_display,
            f'Смена {rec.shift}' if rec.shift else '—',
            section_name,
            rec.report.name,
            rec.row_number,
            rec.name,
            rec.group,
            rec.engine_time_str(),
            rec.fuel_actual,
            rec.fuel_norm,
            fuel_eff_pct,
            output_pct,
            type_eff_pct,
            over_str,
            rec.mileage,
            rec.refueling,
            '; '.join(rec.anomaly_details) if rec.has_anomaly else '',
            rec.comment,
        ]
        for col_idx, val in enumerate(row_data, 1):
            c = ws.cell(row=row_idx, column=col_idx, value=val)
            c.font = Font(size=10, name='Calibri')
            c.alignment = Alignment(horizontal='center', vertical='center')
            s = Side(style='thin', color='BFBFBF')
            c.border = Border(left=s, right=s, top=s, bottom=s)
        if rec.has_anomaly:
            for col_idx in range(1, len(headers) + 1):
                ws.cell(row=row_idx, column=col_idx).fill = PatternFill('solid', fgColor=YELLOW_BG)

    col_widths = [12, 10, 16, 25, 5, 28, 14, 14, 14, 10, 14, 14, 14, 14, 12, 12, 45, 35]
    for i, w in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    period_str = f'{date_from}__{date_to}' if date_from or date_to else 'все'
    filename = f'records_{period_str}.xlsx'
    response = HttpResponse(
        buf.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def _build_excel_workbook(report, all_records, summary):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    from collections import defaultdict

    DARK_BLUE = '1F3864'
    MID_BLUE  = '2E75B6'
    YELLOW_BG = 'FFF2CC'
    ORANGE_BG = 'FCE4D6'
    GREEN_BG  = 'E2EFDA'
    RED_BG    = 'FFE0E0'
    GREY_BG   = 'F2F2F2'
    GROUP_BG  = 'D6E4F0'
    TOTAL_BG  = 'BDD7EE'

    def make_font(bold=False, color='000000', size=10, name='Calibri'):
        return Font(bold=bold, color=color, size=size, name=name)

    def make_fill(color):
        return PatternFill('solid', fgColor=color)

    def make_align(h='center', v='center', wrap=False):
        return Alignment(horizontal=h, vertical=v, wrap_text=wrap)

    def thin_border():
        s = Side(style='thin', color='BFBFBF')
        return Border(left=s, right=s, top=s, bottom=s)

    def pct_fill(val, good_max, warn_max):
        if val is None:
            return None
        if val <= good_max:
            return make_fill(GREEN_BG)
        if val <= warn_max:
            return make_fill(YELLOW_BG)
        return make_fill(ORANGE_BG)

    # ── Columns (18 total) ─────────────────────────────────────────────
    # 1  №
    # 2  Техника
    # 3  Группа
    # 4  Дата
    # 5  Смена
    # 6  Время работы (чч:мм:сс)
    # 7  Факт. расход (л)
    # 8  Норма расхода (л/ч)
    # 9  Расход к норме (%)
    # 10 Выход техники (%)
    # 11 Эффективность (%)
    # 12 Тип эффективности
    # 13 Норма б/д (чч:мм:сс)    ← dump trucks
    # 14 Превышение нормы б/д     ← dump trucks >100 %
    # 15 Пробег (км)
    # 16 Заправка (л)
    # 17 Аномалии
    # 18 Комментарий
    NCOLS = 18

    # Load per-day per-shift dump truck norms for this report
    dt_norms = {
        (vn.vehicle_name, vn.shift, vn.date): vn.dumptruck_norm_sec
        for vn in VehicleNorm.objects.filter(report=report)
    }

    wb = openpyxl.Workbook()
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

    write_merged(1, f'Анализ эффективности техники — {report.name}', DARK_BLUE, size=13)
    ws.row_dimensions[1].height = 28

    section_name = report.section.name if report.section else '—'
    period_text = f'Период: {report.period} | Участок: {section_name}'
    write_merged(2, period_text, 'E8F0FB', '595959', bold=False, size=10)

    norm_row = [
        'Норма/смену:', report.daily_norm_str(),
        'Хол.ход (бульдозеры):', report.bulldozer_norm_str(),
        'Простой стрелы (экскаваторы):', report.excavator_norm_str(),
    ] + [None] * (NCOLS - 6)
    ws.append(norm_row)
    for col in range(1, NCOLS + 1):
        c = ws.cell(row=3, column=col)
        c.font = Font(bold=(col % 2 == 1), size=9, name='Calibri', color='444444')
        c.fill = make_fill(GREY_BG)
        c.alignment = make_align('center')

    ws.append([])

    COL_HEADERS = [
        '№',
        'Техника',
        'Группа',
        'Дата',
        'Смена',
        'Время работы\n(чч:мм:сс)',
        'Факт. расход\n(л)',
        'Норма расхода\n(л/ч)',
        'Расход\nк норме (%)',
        'Выход\nтехники (%)',
        'Эффективность\n(%)',
        'Тип\nэффективности',
        'Норма\nб/д (чч:мм:сс)',
        'Превышение\nнормы б/д',
        'Пробег\n(км)',
        'Заправка\n(л)',
        'Аномалии',
        'Комментарий',
    ]
    ws.append(COL_HEADERS)
    HDR_ROW = 5
    for col in range(1, NCOLS + 1):
        c = ws.cell(row=HDR_ROW, column=col)
        c.font = Font(bold=True, color='FFFFFF', size=10, name='Calibri')
        c.fill = make_fill(MID_BLUE)
        c.alignment = make_align('center', wrap=True)
        c.border = thin_border()
    ws.row_dimensions[HDR_ROW].height = 40
    ws.freeze_panes = f'A{HDR_ROW + 1}'

    records_by_group = defaultdict(list)
    for rec in all_records:
        records_by_group[rec.group].append(rec)

    for group_name in sorted(records_by_group.keys()):
        group_records = records_by_group[group_name]

        ws.append([])
        gr = ws.max_row
        ws.merge_cells(f'A{gr}:{get_column_letter(NCOLS)}{gr}')
        gc = ws.cell(row=gr, column=1)
        gc.value = f'  {group_name.upper()}  ({len(group_records)} ед.)'
        gc.font = Font(bold=True, color=DARK_BLUE, size=10, name='Calibri')
        gc.fill = make_fill(GROUP_BG)
        gc.alignment = make_align('left')
        ws.row_dimensions[gr].height = 18

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

            # Per-shift dump truck norm and overage
            norm_bd_str = ''
            over_bd_str = ''
            if rec.group == 'Самосвалы':
                norm_sec = dt_norms.get((rec.name, rec.shift))
                if norm_sec:
                    norm_bd_str = secs_to_hhmmss(norm_sec)
                    overage = (rec.engine_no_move_sec or 0) - norm_sec
                    if overage > 0:
                        over_bd_str = f'+{secs_to_hhmmss(overage)}'

            anomaly_text = '; '.join(rec.anomaly_details) if rec.has_anomaly else ''
            date_display = rec.record_date.strftime('%d.%m.%Y') if rec.record_date else rec.date
            shift_display = f'С{rec.shift}' if rec.shift else '—'

            ws.append([
                rec.row_number, rec.name, rec.group, date_display, shift_display,
                rec.engine_time_str(), rec.fuel_actual, rec.fuel_norm,
                fuel_eff_pct, output_pct, type_eff_pct, type_label,
                norm_bd_str, over_bd_str,
                rec.mileage, rec.refueling, anomaly_text, rec.comment,
            ])
            r = ws.max_row
            row_fill = make_fill(YELLOW_BG) if rec.has_anomaly else None

            for col in range(1, NCOLS + 1):
                c = ws.cell(row=r, column=col)
                c.font = make_font()
                c.alignment = make_align()
                c.border = thin_border()
                if row_fill and col not in (9, 10, 11):
                    c.fill = row_fill

            ws.cell(row=r, column=2).alignment = make_align('left')
            ws.cell(row=r, column=17).alignment = make_align('left', wrap=True)
            ws.cell(row=r, column=18).alignment = make_align('left', wrap=True)

            # Расход к норме (col 9)
            f = pct_fill(fuel_eff_pct, 100, 115)
            if f:
                ws.cell(row=r, column=9).fill = f
            # Выход техники (col 10): >=80 green, <80 red
            if output_pct is not None:
                ws.cell(row=r, column=10).fill = make_fill(GREEN_BG) if output_pct >= 80 else make_fill(RED_BG)
            # Эффективность (col 11)
            f = pct_fill(type_eff_pct, 100, 130)
            if f:
                ws.cell(row=r, column=11).fill = f
            # Превышение б/д (col 14): red if overage exists
            if over_bd_str:
                ws.cell(row=r, column=14).fill = make_fill('FFB3B3')
                ws.cell(row=r, column=14).font = Font(bold=True, color='C00000', name='Calibri', size=10)
            # Отрицательный расход (col 7)
            if rec.fuel_actual is not None and rec.fuel_actual < 0:
                ws.cell(row=r, column=7).fill = make_fill('FFB3B3')
                ws.cell(row=r, column=7).font = Font(bold=True, color='C00000', name='Calibri', size=10)

            if rec.fuel_actual and rec.fuel_actual > 0:
                g_fuel_actual_sum += rec.fuel_actual
            g_engine_h_sum += rec.engine_time_sec / 3600
            if fuel_eff_pct is not None:
                g_fuel_eff_vals.append(fuel_eff_pct)
            if output_pct is not None:
                g_output_vals.append(output_pct)
            if type_eff_pct is not None:
                g_type_eff_vals.append(type_eff_pct)
            if rec.has_anomaly:
                g_anomaly_count += 1

        g_avg_fuel = round(sum(g_fuel_eff_vals) / len(g_fuel_eff_vals), 1) if g_fuel_eff_vals else None
        g_avg_out  = round(sum(g_output_vals)    / len(g_output_vals),    1) if g_output_vals    else None
        g_avg_type = round(sum(g_type_eff_vals)  / len(g_type_eff_vals),  1) if g_type_eff_vals  else None

        ws.append([
            '', f'ИТОГО {group_name}', '', '', '',
            f'{round(g_engine_h_sum, 1)} ч', round(g_fuel_actual_sum, 1),
            '', g_avg_fuel, g_avg_out, g_avg_type, '', '', '', '', '',
            f'Аномалий: {g_anomaly_count}' if g_anomaly_count else '', '',
        ])
        tr = ws.max_row
        for col in range(1, NCOLS + 1):
            c = ws.cell(row=tr, column=col)
            c.font = Font(bold=True, size=10, name='Calibri', color=DARK_BLUE)
            c.fill = make_fill(TOTAL_BG)
            c.alignment = make_align('center')
            c.border = thin_border()
        ws.cell(row=tr, column=2).alignment = make_align('left')

    # Column widths: 18 columns
    col_widths = [5, 30, 14, 12, 8, 16, 13, 13, 13, 13, 14, 16, 15, 15, 12, 12, 45, 35]
    for i, w in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    return wb
