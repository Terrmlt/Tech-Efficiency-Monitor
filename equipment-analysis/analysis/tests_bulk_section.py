"""
Regression tests for bulk_section_reassign endpoint.

Verifies:
- Both shifts within the date range get the override applied.
- Records outside the date range are not affected.
- Clearing the override (section_id=null) works.
- The effective-section logic in _build_daily_view_records reflects the override.
"""
import datetime
import json
from django.test import TestCase, Client
from django.contrib.auth.models import User
from .models import Report, Section, VehicleRecord
from .views import _build_daily_view_records


def _make_report(section=None):
    return Report.objects.create(
        name='Test Report',
        section=section,
        daily_norm_sec=36000,
        bulldozer_norm_sec=10800,
        excavator_norm_sec=13200,
        dumptruck_norm_sec=10800,
    )


def _make_record(report, name, date, shift, section=None):
    return VehicleRecord.objects.create(
        report=report,
        section=section,
        name=name,
        group='Экскаваторы',
        date=date.strftime('%d.%m'),
        record_date=date,
        shift=shift,
        engine_time_sec=3600,
        engine_no_move_sec=0,
        engine_idle_sec=0,
        fuel_norm=10,
    )


class BulkSectionReassignTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='teststaff', password='pass', is_staff=True
        )
        self.sec_a = Section.objects.create(name='Участок А')
        self.sec_b = Section.objects.create(name='Участок Б')
        self.report = _make_report(section=self.sec_a)

        self.date_in = datetime.date(2026, 6, 15)
        self.date_out = datetime.date(2026, 6, 20)

        # Two shifts on date_in — should be affected
        self.rec_s1 = _make_record(self.report, 'CAT 123', self.date_in, shift=1)
        self.rec_s2 = _make_record(self.report, 'CAT 123', self.date_in, shift=2)
        # One record outside range — must not be affected
        self.rec_out = _make_record(self.report, 'CAT 123', self.date_out, shift=1)

        self.client = Client()
        self.client.login(username='teststaff', password='pass')

    def _post(self, payload):
        return self.client.post(
            '/records/bulk-section/',
            json.dumps(payload),
            content_type='application/json',
        )

    # ── happy path ─────────────────────────────────────────────────────────────

    def test_both_shifts_updated(self):
        r = self._post({
            'vehicle_name': 'CAT 123',
            'date_from': '2026-06-15',
            'date_to': '2026-06-15',
            'section_id': self.sec_b.pk,
        })
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['updated_count'], 2)
        self.assertEqual(data['section_name'], 'Участок Б')

        self.rec_s1.refresh_from_db()
        self.rec_s2.refresh_from_db()
        self.assertEqual(self.rec_s1.section_id, self.sec_b.pk)
        self.assertEqual(self.rec_s2.section_id, self.sec_b.pk)

    def test_record_outside_range_not_affected(self):
        self._post({
            'vehicle_name': 'CAT 123',
            'date_from': '2026-06-15',
            'date_to': '2026-06-15',
            'section_id': self.sec_b.pk,
        })
        self.rec_out.refresh_from_db()
        self.assertIsNone(self.rec_out.section_id)

    def test_clear_override(self):
        # First set, then clear
        self._post({
            'vehicle_name': 'CAT 123',
            'date_from': '2026-06-15',
            'date_to': '2026-06-15',
            'section_id': self.sec_b.pk,
        })
        r = self._post({
            'vehicle_name': 'CAT 123',
            'date_from': '2026-06-15',
            'date_to': '2026-06-15',
            'section_id': None,
        })
        self.assertTrue(r.json()['ok'])
        self.assertIsNone(r.json()['section_name'])
        self.rec_s1.refresh_from_db()
        self.assertIsNone(self.rec_s1.section_id)

    # ── effective-section rendering ────────────────────────────────────────────

    def test_effective_section_in_daily_view_override(self):
        """daily_total row should reflect per-record override, not report section."""
        self.rec_s1.section = self.sec_b
        self.rec_s1.save(update_fields=['section'])
        self.rec_s2.section = self.sec_b
        self.rec_s2.save(update_fields=['section'])

        from analysis.models import VehicleRecord as VR
        qs = VR.objects.select_related('report', 'report__section', 'section').filter(
            report=self.report, name='CAT 123', record_date=self.date_in
        )
        rows = _build_daily_view_records(qs)
        daily_total = next(r for r in rows if r['type'] == 'daily_total')
        self.assertEqual(daily_total['effective_section_name'], 'Участок Б')

    def test_effective_section_falls_back_to_report(self):
        """When no per-record override, daily_total shows report section."""
        qs = VehicleRecord.objects.select_related('report', 'report__section', 'section').filter(
            report=self.report, name='CAT 123', record_date=self.date_in
        )
        rows = _build_daily_view_records(qs)
        daily_total = next(r for r in rows if r['type'] == 'daily_total')
        self.assertEqual(daily_total['effective_section_name'], 'Участок А')

    # ── validation ─────────────────────────────────────────────────────────────

    def test_missing_vehicle_name(self):
        r = self._post({'vehicle_name': '', 'date_from': '2026-06-15', 'date_to': '2026-06-15'})
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.json()['ok'])

    def test_missing_dates(self):
        r = self._post({'vehicle_name': 'CAT 123', 'date_from': '', 'date_to': ''})
        self.assertEqual(r.status_code, 400)

    def test_invalid_date_format(self):
        r = self._post({'vehicle_name': 'CAT 123', 'date_from': 'not-a-date', 'date_to': '2026-06-15'})
        self.assertEqual(r.status_code, 400)

    def test_date_from_after_date_to(self):
        r = self._post({'vehicle_name': 'CAT 123', 'date_from': '2026-06-20', 'date_to': '2026-06-15'})
        self.assertEqual(r.status_code, 400)

    def test_non_staff_forbidden(self):
        User.objects.create_user(username='regular', password='pass', is_staff=False)
        c = Client()
        c.login(username='regular', password='pass')
        r = c.post('/records/bulk-section/', json.dumps({'vehicle_name': 'CAT 123',
            'date_from': '2026-06-15', 'date_to': '2026-06-15'}),
            content_type='application/json')
        # Staff-required redirects non-staff
        self.assertIn(r.status_code, [302, 403])
