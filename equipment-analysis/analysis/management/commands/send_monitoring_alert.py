"""
Management command: send_monitoring_alert

Checks whether all active MonitoringVehicle entries have a MonitoringRecord
for the previous day (or a date specified via --date). If any are missing,
sends a plain-text email to the configured recipient listing the gaps.
If everything is filled — no email is sent.

Usage:
    python manage.py send_monitoring_alert               # checks yesterday
    python manage.py send_monitoring_alert --date 2026-06-29

Scheduling (cron example — runs every day at 08:00 server time):
    0 8 * * * /path/to/venv/bin/python /path/to/manage.py send_monitoring_alert >> /var/log/monitoring_alert.log 2>&1

Required environment variables (see settings.py):
    EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER,
    EMAIL_HOST_PASSWORD, EMAIL_USE_TLS (or EMAIL_USE_SSL),
    DEFAULT_FROM_EMAIL, MONITORING_ALERT_RECIPIENT
"""
import datetime

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand

from analysis.models import MonitoringVehicle, MonitoringRecord


def get_unfilled_vehicles(check_date):
    """
    Return a list of active MonitoringVehicle objects that have no
    MonitoringRecord for *check_date*.
    """
    filled_ids = MonitoringRecord.objects.filter(date=check_date).values_list('vehicle_id', flat=True)
    return list(
        MonitoringVehicle.objects
        .filter(is_active=True)
        .exclude(id__in=filled_ids)
        .select_related('section')
        .order_by('group', 'order', 'name')
    )


def build_alert_body(check_date, unfilled):
    """Build the plain-text email body listing all unfilled vehicles."""
    lines = [
        f'Мониторинг Омникомм — незаполненные данные за {check_date.strftime("%d.%m.%Y")}',
        '',
        f'Следующие единицы техники не имеют записи мониторинга за {check_date.strftime("%d.%m.%Y")}:',
        '',
    ]
    current_group = None
    for v in unfilled:
        if v.group != current_group:
            current_group = v.group
            lines.append(f'[{current_group}]')
        section = v.section.name if v.section else 'участок не указан'
        lines.append(f'  • {v.name} ({section})')
    lines += [
        '',
        f'Всего не заполнено: {len(unfilled)} ед. техники.',
        '',
        'Это автоматическое уведомление системы мониторинга.',
    ]
    return '\n'.join(lines)


class Command(BaseCommand):
    help = 'Отправить email-уведомление о незаполненных данных мониторинга за предыдущий день'

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            type=str,
            default=None,
            help='Дата для проверки в формате YYYY-MM-DD (по умолчанию — вчера)',
        )

    def handle(self, *args, **options):
        if options['date']:
            try:
                check_date = datetime.date.fromisoformat(options['date'])
            except ValueError:
                self.stderr.write(self.style.ERROR(
                    f"Неверный формат даты: {options['date']}. Используйте YYYY-MM-DD."
                ))
                return
        else:
            check_date = datetime.date.today() - datetime.timedelta(days=1)

        self.stdout.write(f'Проверка мониторинга за {check_date} ...')

        unfilled = get_unfilled_vehicles(check_date)

        if not unfilled:
            self.stdout.write(self.style.SUCCESS(
                f'Все данные за {check_date} заполнены. Письмо не отправляется.'
            ))
            return

        self.stdout.write(self.style.WARNING(
            f'Не заполнено: {len(unfilled)} ед. техники. Отправка письма...'
        ))

        recipient = settings.MONITORING_ALERT_RECIPIENT
        subject = f'[Мониторинг] Незаполненные данные за {check_date.strftime("%d.%m.%Y")}'
        body = build_alert_body(check_date, unfilled)

        from analysis.views import _get_smtp_connection
        conn, from_email = _get_smtp_connection()

        try:
            send_mail(
                subject=subject,
                message=body,
                from_email=from_email,
                recipient_list=[recipient],
                fail_silently=False,
                connection=conn,
            )
            self.stdout.write(self.style.SUCCESS(f'Письмо отправлено на {recipient}.'))
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f'Ошибка при отправке письма: {exc}'))
