from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Report, Section


class ReportsBySectionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='reports-admin',
            password='test-password',
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.north = Section.objects.create(name='Северный участок')
        self.south = Section.objects.create(name='Южный участок')
        self.north_report = Report.objects.create(
            name='Северный отчёт',
            section=self.north,
        )
        self.unassigned_report = Report.objects.create(name='Свободный отчёт')

    def test_root_shows_section_cards_instead_of_report_cards(self):
        response = self.client.get(reverse('index'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Отчёты по участкам')
        self.assertContains(response, 'Северный участок')
        self.assertContains(response, 'Южный участок')
        self.assertContains(response, 'Без участка')
        self.assertNotContains(response, self.north_report.name)
        self.assertNotContains(response, self.unassigned_report.name)

    def test_section_page_only_shows_its_reports(self):
        response = self.client.get(reverse('index'), {'section': self.north.pk})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.north.name)
        self.assertContains(response, self.north_report.name)
        self.assertNotContains(response, self.unassigned_report.name)
        self.assertContains(response, 'Ко всем участкам')

    def test_unassigned_page_only_shows_unassigned_reports(self):
        response = self.client.get(reverse('index'), {'section': 'none'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Без участка')
        self.assertContains(response, self.unassigned_report.name)
        self.assertNotContains(response, self.north_report.name)

    def test_empty_section_has_specific_empty_state(self):
        response = self.client.get(reverse('index'), {'section': self.south.pk})

        self.assertContains(response, 'В этом участке пока нет отчётов')

    def test_invalid_section_returns_not_found(self):
        response = self.client.get(reverse('index'), {'section': 999999})

        self.assertEqual(response.status_code, 404)

    def test_empty_database_has_general_empty_state(self):
        Report.objects.all().delete()
        Section.objects.all().delete()

        response = self.client.get(reverse('index'))

        self.assertContains(response, 'Нет загруженных отчётов')