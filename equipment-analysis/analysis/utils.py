import datetime
import openpyxl
from .models import secs_to_hhmmss


def parse_timedelta_to_seconds(value):
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
    if value is None or value == '-' or value == '':
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def parse_date_string(value):
    """Parse day.month string to (day, month) tuple."""
    if not value:
        return None, None
    s = str(value).strip()
    for sep in ('.', '/', '-'):
        if sep in s:
            parts = s.split(sep)
            try:
                return int(parts[0]), int(parts[1])
            except (ValueError, IndexError):
                pass
    return None, None


def build_record_date(date_str, year):
    """Build a full date from 'DD.MM' string and year integer."""
    day, month = parse_date_string(date_str)
    if day and month and year:
        try:
            return datetime.date(year, month, day)
        except ValueError:
            pass
    return None


def detect_anomalies(record):
    anomalies = []

    engine_time_sec = record.get('engine_time_sec', 0) or 0
    engine_no_move_sec = record.get('engine_no_move_sec', 0) or 0
    engine_idle_sec = record.get('engine_idle_sec', 0) or 0
    fuel_actual = record.get('fuel_actual')
    fuel_norm = record.get('fuel_norm', 0) or 0
    mileage = record.get('mileage')
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

    # Mileage-based anomalies
    if mileage is not None:
        if mileage > 10 and fuel_actual is not None and fuel_actual == 0:
            anomalies.append(
                f'Пробег {mileage:.1f} км при нулевом расходе топлива'
            )
        if mileage > 10 and engine_time_sec == 0:
            anomalies.append(
                f'Пробег {mileage:.1f} км при нулевом времени работы двигателя'
            )
        if mileage == 0 and engine_time_sec > 3600 and fuel_actual is not None and fuel_actual > 0:
            anomalies.append(
                f'Нулевой пробег при работе двигателя {engine_time_hours:.1f} ч и расходе {fuel_actual} л'
            )

    return len(anomalies) > 0, anomalies


def calculate_metrics(record_data, report):
    """
    Formulas:
    1. fuel_efficiency  = fuel_actual / (fuel_norm * daily_norm_hours)
       where daily_norm_hours = daily_norm_sec / 3600
       ratio to norm: 1.0 = exactly on norm, <1 = below (economy), >1 = above (overrun)
    2. equipment_output = engine_time_sec / daily_norm_sec
    3. type_efficiency  (group-specific):
       Бульдозеры/Погрузчики : engine_idle_sec    / bulldozer_norm_sec
       Экскаваторы           : downtime_sec        / excavator_norm_sec
       Самосвалы             : engine_no_move_sec  / dumptruck_norm_sec
    """
    engine_time_sec = record_data.get('engine_time_sec', 0) or 0
    engine_no_move_sec = record_data.get('engine_no_move_sec', 0) or 0
    engine_idle_sec = record_data.get('engine_idle_sec', 0) or 0
    fuel_actual = record_data.get('fuel_actual')
    fuel_norm = record_data.get('fuel_norm', 0) or 0
    downtime_sec = record_data.get('downtime_sec')
    group = record_data.get('group', '')

    daily_norm_hours = report.daily_norm_sec / 3600 if report.daily_norm_sec > 0 else 0

    # 1. Расход к норме: факт / (норма л/ч × норма смены ч)
    fuel_efficiency = None
    if (fuel_actual is not None and fuel_actual >= 0
            and daily_norm_hours > 0 and fuel_norm > 0):
        denominator = fuel_norm * daily_norm_hours
        if denominator > 0:
            fuel_efficiency = fuel_actual / denominator

    # 2. Выход техники
    equipment_output = None
    if report.daily_norm_sec > 0:
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


def _find_column_indices(header_row):
    """
    Try to find column indices by header name.
    Returns dict mapping field name -> column index (0-based).
    Falls back to default positions if headers not found.
    """
    defaults = {
        'row_number': 0,
        'name': 1,
        'group': 2,
        'date': 3,
        'engine_time': 4,
        'engine_no_move': 6,
        'engine_idle': 8,
        'fuel_norm': 10,
        'fuel_actual': 11,
        'downtime': 12,
        'mileage': None,
        'refueling': None,
    }

    if not header_row or all(c is None for c in header_row):
        return defaults

    header_lower = [str(c).lower().strip() if c else '' for c in header_row]

    keywords = {
        'mileage': ['пробег', 'km', 'км'],
        'refueling': ['заправк', 'топливо заправ', 'объём заправ', 'объем заправ'],
        'downtime': ['простой', 'простоя', 'простоя стрелы', 'время простоя'],
        'fuel_actual': ['фактический расход', 'расход факт', 'факт. расход'],
    }

    for field, kws in keywords.items():
        for i, h in enumerate(header_lower):
            for kw in kws:
                if kw in h:
                    defaults[field] = i
                    break

    return defaults


def parse_excel_file(file_path):
    wb = openpyxl.load_workbook(file_path, data_only=True)
    ws = wb.active

    metadata = {'period': '', 'vehicles_list': '', 'report_name': ''}
    records = []

    # Read metadata from first rows
    for row in ws.iter_rows(min_row=1, max_row=9, values_only=True):
        if row[0] == 'Отчет:' and len(row) > 1 and row[1]:
            metadata['report_name'] = str(row[1]).strip()
        elif row[0] == 'Период:' and len(row) > 1 and row[1]:
            metadata['period'] = str(row[1]).strip()
        elif row[0] == 'Транспортные средства:' and len(row) > 1 and row[1]:
            metadata['vehicles_list'] = str(row[1]).strip()

    # Try to detect column layout from first data-ish row
    cols = None
    for row in ws.iter_rows(min_row=7, max_row=11, values_only=True):
        if row[0] is not None:
            cols = _find_column_indices(row)
            break

    if cols is None:
        cols = _find_column_indices([])

    for row in ws.iter_rows(min_row=10, values_only=True):
        if row[0] is None:
            continue

        def get(idx):
            if idx is None or idx >= len(row):
                return None
            return row[idx]

        engine_time_sec    = parse_timedelta_to_seconds(get(cols['engine_time'])) or 0
        engine_no_move_sec = parse_timedelta_to_seconds(get(cols['engine_no_move'])) or 0
        engine_idle_sec    = parse_timedelta_to_seconds(get(cols['engine_idle'])) or 0
        fuel_norm          = parse_float(get(cols['fuel_norm'])) or 0
        fuel_actual        = parse_float(get(cols['fuel_actual']))
        downtime_sec       = parse_timedelta_to_seconds(get(cols['downtime']))
        mileage            = parse_float(get(cols['mileage']))
        refueling          = parse_float(get(cols['refueling']))

        try:
            row_num = int(str(row[cols['row_number']]).strip())
        except (ValueError, TypeError):
            row_num = 0

        date_val = get(cols['date'])
        if isinstance(date_val, (datetime.date, datetime.datetime)):
            date_str = date_val.strftime('%d.%m')
        else:
            date_str = str(date_val) if date_val else ''

        records.append({
            'row_number': row_num,
            'name': str(get(cols['name'])) if get(cols['name']) else '',
            'group': str(get(cols['group'])) if get(cols['group']) else '',
            'date': date_str,
            'engine_time_sec': engine_time_sec,
            'engine_no_move_sec': engine_no_move_sec,
            'engine_idle_sec': engine_idle_sec,
            'fuel_norm': fuel_norm,
            'fuel_actual': fuel_actual,
            'downtime_sec': downtime_sec,
            'mileage': mileage,
            'refueling': refueling,
        })

    return metadata, records


def build_summary(vehicle_records, report):
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
