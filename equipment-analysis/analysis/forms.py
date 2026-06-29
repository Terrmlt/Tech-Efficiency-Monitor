import re
import datetime
from django import forms
from django.contrib.auth.models import User, Group
from .models import Report, Section, UserProfile


def parse_hhmmss(value):
    value = (value or '').strip()
    m = re.fullmatch(r'(\d{1,3}):([0-5]\d):([0-5]\d)', value)
    if not m:
        raise forms.ValidationError('Введите время в формате ЧЧ:ММ:СС (например 10:00:00)')
    h, mn, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return h * 3600 + mn * 60 + s


TIME_INPUT_ATTRS = {
    'class': 'form-control',
    'placeholder': 'ЧЧ:ММ:СС',
    'pattern': r'\d{1,3}:[0-5]\d:[0-5]\d',
}


class SectionForm(forms.ModelForm):
    class Meta:
        model = Section
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Название участка',
            }),
        }
        labels = {'name': 'Название участка'}


class ReportUploadForm(forms.ModelForm):
    section = forms.ModelChoiceField(
        queryset=Section.objects.all(),
        required=False,
        empty_label='— Выберите участок —',
        label='Участок',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    daily_norm = forms.CharField(
        initial='10:00:00',
        label='Норма работы в смену',
        help_text='Плановое время работы двигателя за смену (обычно 10:00:00)',
        widget=forms.TextInput(attrs=TIME_INPUT_ATTRS),
    )
    bulldozer_norm = forms.CharField(
        initial='02:00:00',
        label='Норма холостого хода — Бульдозеры/Погрузчики',
        help_text='Допустимое время работы двигателя на холостом ходу',
        widget=forms.TextInput(attrs=TIME_INPUT_ATTRS),
    )
    excavator_norm = forms.CharField(
        initial='02:00:00',
        label='Норма простоя стрелы — Экскаваторы',
        help_text='Допустимое время простоя стрелы (колонка «Время простоя»)',
        widget=forms.TextInput(attrs=TIME_INPUT_ATTRS),
    )
    class Meta:
        model = Report
        fields = ['name', 'file']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Например: Отчёт 15.06.2026 Смена 1',
            }),
            'file': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.xlsx,.xls',
            }),
        }
        labels = {
            'name': 'Название отчёта',
            'file': 'Файл Excel (.xlsx)',
        }

    def clean_daily_norm(self):
        return parse_hhmmss(self.cleaned_data['daily_norm'])

    def clean_bulldozer_norm(self):
        return parse_hhmmss(self.cleaned_data['bulldozer_norm'])

    def clean_excavator_norm(self):
        return parse_hhmmss(self.cleaned_data['excavator_norm'])

    def clean_file(self):
        f = self.cleaned_data.get('file')
        if f:
            name = f.name.lower()
            if not (name.endswith('.xlsx') or name.endswith('.xls')):
                raise forms.ValidationError('Поддерживаются только файлы .xlsx и .xls')
        return f

    def save(self, commit=True):
        report = super().save(commit=False)
        report.daily_norm_sec = self.cleaned_data['daily_norm']
        report.bulldozer_norm_sec = self.cleaned_data['bulldozer_norm']
        report.excavator_norm_sec = self.cleaned_data['excavator_norm']
        report.section = self.cleaned_data.get('section')
        if commit:
            report.save()
        return report


class UserCreateForm(forms.Form):
    username = forms.CharField(
        label='Логин',
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'off'}),
    )
    first_name = forms.CharField(
        label='Имя',
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    last_name = forms.CharField(
        label='Фамилия',
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    password = forms.CharField(
        label='Пароль',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'new-password'}),
    )
    group = forms.ModelChoiceField(
        queryset=Group.objects.all(),
        required=False,
        empty_label='— Без группы —',
        label='Группа',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    section = forms.ModelChoiceField(
        queryset=Section.objects.all(),
        required=False,
        empty_label='— Без участка —',
        label='Участок (для группы Мониторинг)',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('Пользователь с таким логином уже существует.')
        return username

    def save(self):
        data = self.cleaned_data
        user = User.objects.create_user(
            username=data['username'],
            password=data['password'],
            first_name=data.get('first_name', ''),
            last_name=data.get('last_name', ''),
        )
        user.groups.set([data['group']] if data.get('group') else [])
        user.save()
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.section = data.get('section')
        profile.save()
        return user


class UserEditForm(forms.Form):
    first_name = forms.CharField(
        label='Имя',
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    last_name = forms.CharField(
        label='Фамилия',
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    group = forms.ModelChoiceField(
        queryset=Group.objects.all(),
        required=False,
        empty_label='— Без группы —',
        label='Группа',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    section = forms.ModelChoiceField(
        queryset=Section.objects.all(),
        required=False,
        empty_label='— Без участка —',
        label='Участок (для группы Мониторинг)',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    new_password = forms.CharField(
        label='Новый пароль',
        required=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'new-password',
                                          'placeholder': 'Оставьте пустым, чтобы не менять'}),
        help_text='Оставьте пустым, чтобы не изменять пароль.',
    )

    def save(self, user):
        data = self.cleaned_data
        user.first_name = data.get('first_name', '')
        user.last_name = data.get('last_name', '')
        if data.get('new_password'):
            user.set_password(data['new_password'])
        user.groups.set([data['group']] if data.get('group') else [])
        user.save()
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.section = data.get('section')
        profile.save()
        return user
