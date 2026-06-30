"""
Management command: import_monitoring_vehicles

Reads all unique (name, group, section) combinations from VehicleRecord
and creates MonitoringVehicle entries for those that don't already exist.
Existing records are never modified or duplicated.

Usage:
    python manage.py import_monitoring_vehicles
"""
from django.core.management.base import BaseCommand
from analysis.models import VehicleRecord, MonitoringVehicle, MONITORING_GROUPS

VALID_GROUPS = {g[0] for g in MONITORING_GROUPS}


def run_import():
    """
    Core import logic, shared with the web view.

    Returns a dict:
        created  — int, how many MonitoringVehicle records were created
        skipped  — int, how many already existed
        unknown  — list of (name, group) tuples whose group is not in MONITORING_GROUPS
    """
    created = 0
    skipped = 0
    unknown = []

    combos = (
        VehicleRecord.objects
        .values('name', 'group', 'report__section_id', 'report__section__name')
        .distinct()
        .order_by('group', 'name')
    )

    for row in combos:
        vehicle_name = row['name']
        vehicle_group = row['group']
        section_id = row['report__section_id']

        if vehicle_group not in VALID_GROUPS:
            unknown.append((vehicle_name, vehicle_group))
            continue

        _, was_created = MonitoringVehicle.objects.get_or_create(
            name=vehicle_name,
            group=vehicle_group,
            section_id=section_id,
        )
        if was_created:
            created += 1
        else:
            skipped += 1

    return {'created': created, 'skipped': skipped, 'unknown': unknown}


class Command(BaseCommand):
    help = 'Импортировать технику из загруженных Excel-отчётов в справочник мониторинга'

    def handle(self, *args, **options):
        result = run_import()

        self.stdout.write(self.style.SUCCESS(
            f"Создано: {result['created']} единиц техники."
        ))
        self.stdout.write(
            f"Пропущено (уже существуют): {result['skipped']}."
        )
        if result['unknown']:
            self.stdout.write(self.style.WARNING(
                f"Не удалось сопоставить с группой ({len(result['unknown'])} шт.):"
            ))
            seen = set()
            for name, group in result['unknown']:
                key = (name, group)
                if key not in seen:
                    seen.add(key)
                    self.stdout.write(f"  {name!r} → группа {group!r}")
