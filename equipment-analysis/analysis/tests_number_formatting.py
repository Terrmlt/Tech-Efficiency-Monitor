from decimal import Decimal

from django.test import SimpleTestCase
from openpyxl import Workbook

from .templatetags.analysis_extras import ru_number
from .views import _apply_excel_number_formats


class RussianNumberFormattingTests(SimpleTestCase):
    def test_formats_integer_with_grouping(self):
        self.assertEqual(ru_number(1234567), '1 234 567')

    def test_formats_decimal_with_comma_and_preserves_precision(self):
        self.assertEqual(ru_number(Decimal('1234567.89')), '1 234 567,89')
        self.assertEqual(ru_number(Decimal('12.50')), '12,50')

    def test_formats_negative_zero_and_empty_values(self):
        self.assertEqual(ru_number(Decimal('-1234.5')), '-1 234,5')
        self.assertEqual(ru_number(0), '0')
        self.assertEqual(ru_number(None), '')

    def test_leaves_non_numeric_identifiers_unchanged(self):
        self.assertEqual(ru_number('№305'), '№305')

    def test_excel_values_remain_numeric_and_receive_formats(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append([1234567, 1234567.89, '№305'])

        _apply_excel_number_formats(workbook)

        self.assertEqual(sheet['A1'].value, 1234567)
        self.assertEqual(sheet['A1'].number_format, '# ##0')
        self.assertEqual(sheet['B1'].value, 1234567.89)
        self.assertEqual(sheet['B1'].number_format, '# ##0.00##########')
        self.assertEqual(sheet['C1'].number_format, 'General')