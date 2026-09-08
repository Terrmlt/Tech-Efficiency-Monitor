import datetime

from django.contrib.auth.models import User
from django.test import TestCase

from .models import Report, Section, VehicleRecord
from .views import _extract_board_number


class RecordsBoardSortingTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username='records-staff', password='pass', is_staff=True
        )
        section = Section.objects.create(name='Участок')
        report = Report.objects.create(
            name='Сортировка',
            section=section,
            daily_norm_sec=36000,
            bulldozer_norm_sec=10800,
            excavator_norm_sec=13200,
            dumptruck_norm_sec=10800,
        )
        record_date = datetime.date.today()
        for row_number, name in enumerate(
            ['Volvo №80', 'Без бортового номера', 'Volvo №9'], start=1
        ):
            VehicleRecord.objects.create(
                report=report,
                row_number=row_number,
                name=name,
                group='Самосвалы',
                date=record_date.strftime('%d.%m'),
                record_date=record_date,
                shift=1,
                engine_time_sec=3600,
                fuel_norm=30,
            )
        self.client.login(username='records-staff', password='pass')

    def test_extracts_numeric_board_number(self):
        self.assertEqual(_extract_board_number('Volvo № 009'), 9)
        self.assertEqual(_extract_board_number('CAT №:352'), 352)
        self.assertIsNone(_extract_board_number('Техника без номера'))

    def test_board_sort_is_numeric_and_places_missing_last(self):
        response = self.client.get('/records/', {'sort': 'board'})
        names = [
            row['obj'].name
            for row in response.context['daily_view']
            if row['type'] == 'record'
        ]

        self.assertEqual(names, ['Volvo №9', 'Volvo №80', 'Без бортового номера'])
        self.assertEqual(response.context['sort_filter'], 'board')
        self.assertIn('sort=board', response.context['filter_qs'])

    def test_rendered_page_keeps_sort_control_and_block_boundaries(self):
        response = self.client.get('/records/', {'sort': 'board'})
        html = response.content.decode()

        self.assertIn('value="board" selected', html)
        self.assertIn('equipment-block-start', html)
        self.assertIn('Борт № 9', html)
        self.assertIn('comment-saving', html)

    def test_board_sort_uses_primary_key_as_final_tie_breaker(self):
        original = VehicleRecord.objects.get(name='Volvo №9')
        duplicate = VehicleRecord.objects.create(
            report=original.report,
            row_number=original.row_number,
            name=original.name,
            group=original.group,
            date=original.date,
            record_date=original.record_date,
            shift=original.shift,
            engine_time_sec=original.engine_time_sec,
            fuel_norm=original.fuel_norm,
        )

        response = self.client.get('/records/', {'sort': 'board'})
        matching_ids = [
            row['obj'].pk
            for row in response.context['daily_view']
            if row['type'] == 'record' and row['obj'].name == 'Volvo №9'
        ]

        self.assertEqual(matching_ids, [original.pk, duplicate.pk])