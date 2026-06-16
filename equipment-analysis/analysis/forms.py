from django import forms
from .models import Report


class ReportUploadForm(forms.ModelForm):
    class Meta:
        model = Report
        fields = [
            'name', 'file',
            'daily_norm_hours',
            'bulldozer_idle_norm_pct',
            'excavator_downtime_norm_pct',
            'dumptruck_nomove_norm_pct',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Например: Отчёт за 15.06.2026',
            }),
            'file': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.xlsx,.xls',
            }),
            'daily_norm_hours': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.5',
                'min': '1',
                'max': '24',
            }),
            'bulldozer_idle_norm_pct': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '1',
                'min': '0',
                'max': '100',
            }),
            'excavator_downtime_norm_pct': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '1',
                'min': '0',
                'max': '100',
            }),
            'dumptruck_nomove_norm_pct': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '1',
                'min': '0',
                'max': '100',
            }),
        }
        labels = {
            'name': 'Название отчёта',
            'file': 'Файл Excel (.xlsx)',
            'daily_norm_hours': 'Норма работы в сутки (часов)',
            'bulldozer_idle_norm_pct': 'Норма холостого хода — Бульдозеры/Погрузчики (% от времени работы)',
            'excavator_downtime_norm_pct': 'Норма простоя стрелы — Экскаваторы (% от времени работы)',
            'dumptruck_nomove_norm_pct': 'Норма без движения — Самосвалы (% от времени работы)',
        }
        help_texts = {
            'daily_norm_hours': 'Сколько часов в день должна работать техника по плану',
            'bulldozer_idle_norm_pct': 'Допустимый % времени на холостом ходу',
            'excavator_downtime_norm_pct': 'Допустимый % времени простоя стрелы',
            'dumptruck_nomove_norm_pct': 'Допустимый % времени работы двигателя без движения',
        }

    def clean_file(self):
        f = self.cleaned_data.get('file')
        if f:
            name = f.name.lower()
            if not (name.endswith('.xlsx') or name.endswith('.xls')):
                raise forms.ValidationError('Поддерживаются только файлы .xlsx и .xls')
        return f
