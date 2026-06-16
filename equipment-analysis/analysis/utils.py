import datetime
import openpyxl
from .models import secs_to_hhmmss


def parse_timedelta_to_seconds(value):
    """Convert timedelta, string HH:MM:SS, or '-' to seconds."""
    if value is None or value == '-' or value == '':
        return None
    if isinstance(value, datetime.timedelta):
        return value.total_seconds()
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        value = value.strip()
        if value == '-':
            return None
        parts = value.split(':')
        if len(parts) == 3:
            try:
                h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
                return h * 3600 + m * 60 + s
            except ValueError:
                return None
    return None


def parse_float(value):
    """Parse a numeric value, return None for '-' or None."""
    if value is None or value == '-' or value == '':
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def detect_anomalies(record):
    """
    Detect anomalies in a vehicle record.
    Returns (has_anomaly, list_of_anomaly_descriptions).
    """
    anomalies = []

    engine_time_sec = record.get('engine_time_sec', 0) or 0
    engine_no_move_sec = record.get('engine_no_move_sec', 0) or 0
    engine_idle_sec = record.get('engine_idle_sec', 0) or 0
    fuel_actual = record.get('fuel_actual')
    fuel_norm = record.get('fuel_norm', 0) or 0
    engine_time_hours = engine_time_sec / 3600

    if fuel_actual is not None and fuel_actual < 0:
        anomalies.append(f'Отрицательный расход топлива: {fuel_actual} л')

    if engine_time_hours >= 8 and fuel_actual is not None and fuel_actual == 0:
        anomalies.append(
            f'Техника работала {engine_time_hours:.1f} ч при нулевом расходе топлива'
        )
    elif engine_time_sec > 600 and fuel_actual is not None and fuel_actual == 0:
        anomalies.append(
            f'Работа двигателя {engine_time_hours:.1f} ч без расхода топлива'
        )

    if engine_time_sec > 0 and engine_idle_sec > engine_time_sec:
        anomalies.append(
            f'Холостой ход ({secs_to_hhmmss(engine_idle_sec)}) превышает время работы двигателя ({secs_to_hhmmss(engine_time_sec)})'
        )

    if engine_time_sec > 0 and engine_no_move_sec > engine_time_sec:
        anomalies.append(
            f'Время без движения ({secs_to_hhmmss(engine_no_move_sec)}) превышает время работы двигателя ({secs_to_hhmmss(engine_time_sec)})'
        )

    if fuel_norm > 0 and fuel_actual is not None and fuel_actual > 0 and engine_time_hours > 0:
        actual_rate = fuel_actual / engine_time_hours
        if actual_rate > fuel_norm * 3:
            anomalies.append(
                f'Расход топлива ({actual_rate:.1f} л/ч) превышает норму более чем в 3 раза (норма: {fuel_norm} л/ч)'
            )

    if engine_time_sec == 0 and fuel_actual is not None and fuel_actual > 0:
        anomalies.append(
            f'Зафиксирован расход топлива ({fuel_actual} л) при нулевом времени работы двигателя'
        )

    return len(anomalies) > 0, anomalies


def calculate_metrics(record_data, report):
    """
    Calculate efficiency metrics for a vehicle record.

    Formulas:
    1. fuel_efficiency  = fuel_actual / (fuel_norm * engine_time_hours)
       ratio to norm: 1.0 = exactly on norm, <1 = below norm, >1 = above norm
    2. equipment_output = engine_time_sec / daily_norm_sec
    3. type_efficiency  = actual_time_sec / norm_time_sec  (group-specific)
       Бульдозеры/Погрузчики : engine_idle_sec  / bulldozer_norm_sec
       Экскаваторы           : downtime_sec      / excavator_norm_sec
       Самосвалы             : engine_no_move_sec / dumptruck_norm_sec
    """
    engine_time_sec = record_data.get('engine_time_sec', 0) or 0
    engine_no_move_sec = record_data.get('engine_no_move_sec', 0) or 0
    engine_idle_sec = record_data.get('engine_idle_sec', 0) or 0
    fuel_actual = record_data.get('fuel_actual')
    fuel_norm = record_data.get('fuel_norm', 0) or 0
    downtime_sec = record_data.get('downtime_sec')
    group = record_data.get('group', '')

    engine_time_hours = engine_time_sec / 3600

    # 1. Расход к норме
    fuel_efficiency = None
    if (fuel_actual is not None and fuel_actual > 0
            and engine_time_hours > 0 and fuel_norm > 0):
        fuel_efficiency = fuel_actual / (fuel_norm * engine_time_hours)

    # 2. Выход техники
    equipment_output = None
    if engine_time_sec > 0 and report.daily_norm_sec > 0:
        equipment_output = engine_time_sec / report.daily_norm_sec

    # 3. Эффективность по типу
    type_efficiency = None

    if group in ('Бульдозеры', 'Погрузчики'):
        if report.bulldozer_norm_sec > 0:
            type_efficiency = engine_idle_sec / report.bulldozer_norm_sec

    elif group == 'Экскаваторы':
        if downtime_sec is not None and report.excavator_norm_sec > 0:
            type_efficiency = downtime_sec / report.excavator_norm_sec

    elif group == 'Самосвалы':
        if report.dumptruck_norm_sec > 0:
            type_efficiency = engine_no_move_sec / report.dumptruck_norm_sec

    return {
        'fuel_efficiency': fuel_efficiency,
        'equipment_output': equipment_output,
        'type_efficiency': type_efficiency,
    }


def parse_excel_file(file_path):
    """
    Parse the Excel report file.
    Returns metadata dict and list of vehicle record dicts.
    """
    wb = openpyxl.load_workbook(file_path, data_only=True)
    ws = wb.active

    metadata = {'period': '', 'vehicles_list': '', 'report_name': ''}
    records = []

    for row in ws.iter_rows(min_row=1, max_row=9, values_only=True):
        if row[0] == 'Отчет:' and row[1]:
            metadata['report_name'] = str(row[1]).strip()
        elif row[0] == 'Период:' and row[1]:
            metadata['period'] = str(row[1]).strip()
        elif row[0] == 'Транспортные средства:' and row[1]:
            metadata['vehicles_list'] = str(row[1]).strip()

    for row in ws.iter_rows(min_row=10, values_only=True):
        if row[0] is None:
            continue

        engine_time_sec    = parse_timedelta_to_seconds(row[4]) or 0
        engine_no_move_sec = parse_timedelta_to_seconds(row[6]) or 0
        engine_idle_sec    = parse_timedelta_to_seconds(row[8]) or 0
        fuel_norm          = parse_float(row[10]) or 0
        fuel_actual        = parse_float(row[11])
        downtime_sec       = parse_timedelta_to_seconds(row[12])

        try:
            row_num = int(str(row[0]).strip())
        except (ValueError, TypeError):
            row_num = 0

        records.append({
            'row_number': row_num,
            'name': str(row[1]) if row[1] else '',
            'group': str(row[2]) if row[2] else '',
            'date': str(row[3]) if row[3] else '',
            'engine_time_sec': engine_time_sec,
            'engine_no_move_sec': engine_no_move_sec,
            'engine_idle_sec': engine_idle_sec,
            'fuel_norm': fuel_norm,
            'fuel_actual': fuel_actual,
            'downtime_sec': downtime_sec,
        })

    return metadata, records


def build_summary(vehicle_records, report):
    """Build per-group summary statistics."""
    from collections import defaultdict

    groups = defaultdict(lambda: {
        'count': 0, 'anomaly_count': 0,
        'total_engine_hours': 0, 'total_fuel_actual': 0,
        'fuel_eff_sum': 0, 'fuel_eff_count': 0,
        'output_sum': 0, 'output_count': 0,
        'type_eff_sum': 0, 'type_eff_count': 0,
    })

    for rec in vehicle_records:
        g = groups[rec.group]
        g['count'] += 1
        if rec.has_anomaly:
            g['anomaly_count'] += 1
        g['total_engine_hours'] += rec.engine_time_sec / 3600
        if rec.fuel_actual is not None and rec.fuel_actual > 0:
            g['total_fuel_actual'] += rec.fuel_actual
        if rec.fuel_efficiency is not None:
            g['fuel_eff_sum'] += rec.fuel_efficiency
            g['fuel_eff_count'] += 1
        if rec.equipment_output is not None:
            g['output_sum'] += rec.equipment_output
            g['output_count'] += 1
        if rec.type_efficiency is not None:
            g['type_eff_sum'] += rec.type_efficiency
            g['type_eff_count'] += 1

    summary = []
    for group_name, data in sorted(groups.items()):
        avg_fuel_eff = (data['fuel_eff_sum'] / data['fuel_eff_count'] * 100) if data['fuel_eff_count'] > 0 else None
        avg_output   = (data['output_sum']   / data['output_count']   * 100) if data['output_count']   > 0 else None
        avg_type_eff = (data['type_eff_sum'] / data['type_eff_count'] * 100) if data['type_eff_count'] > 0 else None

        type_eff_label = {
            'Бульдозеры': f'Холостой ход к норме ({report.bulldozer_norm_str()})',
            'Погрузчики': f'Холостой ход к норме ({report.bulldozer_norm_str()})',
            'Экскаваторы': f'Простой стрелы к норме ({report.excavator_norm_str()})',
            'Самосвалы': f'Без движения к норме ({report.dumptruck_norm_str()})',
        }.get(group_name, 'Эффективность')

        summary.append({
            'group': group_name,
            'count': data['count'],
            'anomaly_count': data['anomaly_count'],
            'total_engine_hours': round(data['total_engine_hours'], 1),
            'total_fuel_actual': round(data['total_fuel_actual'], 1),
            'avg_fuel_eff': round(avg_fuel_eff, 1) if avg_fuel_eff is not None else None,
            'avg_output':   round(avg_output,   1) if avg_output   is not None else None,
            'avg_type_eff': round(avg_type_eff, 1) if avg_type_eff is not None else None,
            'type_eff_label': type_eff_label,
        })

    return summary
