import datetime
import io

import openpyxl
from django.contrib.auth.models import Group, User
from django.test import TestCase

from .models import Report, Section, VehicleRecord


class AnalyticsExportTests(TestCase):
    def setUp(self):
        analyst_group = Group.objects.create(name='Аналитика')
        self.analyst = User.objects.create_user(username='analyst', password='pass')
        self.analyst.groups.add(analyst_group)
        self.section = Section.objects.create(name='Карьер')
        self.report = Report.objects.create(
            name='Проверочный отчёт',
            section=self.section,
            daily_norm_sec=36000,
            bulldozer_norm_sec=10800,
            excavator_norm_sec=13200,
            dumptruck_norm_sec=10800,
        )
        self.record = VehicleRecord.objects.create(
            report=self.report,
            row_number=1,
            name='Volvo A40F №352',
            group='Самосвалы',
            date='08.09',
            record_date=datetime.date.today(),
            shift=1,
            engine_time_sec=3600,
            fuel_actual=120,
            fuel_norm=30,
            fuel_efficiency=0.8,
            mileage=54.5,
            refueling=25,
        )
        self.client.login(username='analyst', password='pass')

    def test_analytics_defaults_to_last_30_days(self):
        response = self.client.get('/analytics/')
        today = datetime.date.today()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['date_from'], (today - datetime.timedelta(days=30)).isoformat())
        self.assertEqual(response.context['date_to'], today.isoformat())

    def test_vehicle_search_matches_name_and_board_number(self):
        by_name = self.client.get('/analytics/', {
            'date_from': '2000-01-01',
            'date_to': '2100-01-01',
            'vehicle_search': 'volvo',
        })
        by_number = self.client.get('/analytics/', {
            'date_from': '2000-01-01',
            'date_to': '2100-01-01',
            'vehicle_search': '352',
        })

        self.assertEqual(by_name.context['total_count'], 1)
        self.assertEqual(by_number.context['total_count'], 1)

    def test_vehicle_search_is_unicode_case_insensitive(self):
        self.record.name = 'БелАЗ №352'
        self.record.save(update_fields=['name'])

        response = self.client.get('/analytics/', {
            'date_from': '2000-01-01',
            'date_to': '2100-01-01',
            'vehicle_search': 'белаз',
        })

        self.assertEqual(response.context['total_count'], 1)

    def test_export_uses_allowlisted_selected_columns(self):
        response = self.client.get('/analytics/export/', {
            'dataset': 'fuel',
            'date_from': '2000-01-01',
            'date_to': '2100-01-01',
            'columns': ['vehicle', 'fuel_actual', 'password'],
        })

        self.assertEqual(response.status_code, 200)
        workbook = openpyxl.load_workbook(io.BytesIO(response.content))
        headers = [cell.value for cell in workbook.active[1]]
        self.assertEqual(headers, ['Техника', 'Фактический расход, л'])

    def test_export_supports_legacy_vehicle_filter(self):
        VehicleRecord.objects.create(
            report=self.report,
            row_number=2,
            name='CAT 777 №100',
            group='Самосвалы',
            date='08.09',
            record_date=datetime.date.today(),
            shift=1,
            engine_time_sec=3600,
            fuel_actual=80,
            fuel_norm=30,
        )

        response = self.client.get('/analytics/export/', {
            'dataset': 'fuel',
            'vehicle': 'volvo',
            'columns': ['vehicle'],
        })
        workbook = openpyxl.load_workbook(io.BytesIO(response.content))
        data_rows = list(workbook.active.iter_rows(min_row=2, values_only=True))

        self.assertEqual(data_rows, [('Volvo A40F №352',)])

    def test_mileage_export_excludes_missing_values(self):
        VehicleRecord.objects.create(
            report=self.report,
            row_number=2,
            name='Volvo A40F №353',
            group='Самосвалы',
            date='08.09',
            record_date=datetime.date.today(),
            shift=1,
            engine_time_sec=3600,
            fuel_norm=30,
            mileage=None,
        )

        response = self.client.get('/analytics/export/', {
            'dataset': 'mileage',
            'date_from': '2000-01-01',
            'date_to': '2100-01-01',
            'columns': ['vehicle', 'mileage'],
        })
        workbook = openpyxl.load_workbook(io.BytesIO(response.content))
        data_rows = list(workbook.active.iter_rows(min_row=2, values_only=True))

        self.assertEqual(data_rows, [('Volvo A40F №352', 54.5)])

    def test_direct_export_defaults_to_last_30_days(self):
        VehicleRecord.objects.create(
            report=self.report,
            row_number=3,
            name='Старая техника №1',
            group='Самосвалы',
            date='01.01',
            record_date=datetime.date.today() - datetime.timedelta(days=90),
            shift=1,
            engine_time_sec=3600,
            fuel_actual=10,
            fuel_norm=30,
        )

        response = self.client.get('/analytics/export/', {
            'dataset': 'fuel',
            'columns': ['vehicle'],
        })
        workbook = openpyxl.load_workbook(io.BytesIO(response.content))
        data_rows = list(workbook.active.iter_rows(min_row=2, values_only=True))

        self.assertEqual(data_rows, [('Volvo A40F №352',)])

    def test_export_escapes_formula_leading_text(self):
        self.record.name = '=HYPERLINK(\"https://example.test\")'
        self.record.save(update_fields=['name'])

        response = self.client.get('/analytics/export/', {
            'dataset': 'fuel',
            'columns': ['vehicle'],
        })
        workbook = openpyxl.load_workbook(io.BytesIO(response.content), data_only=False)
        value = workbook.active.cell(row=2, column=1).value

        self.assertEqual(value, '\'=HYPERLINK(\"https://example.test\")')