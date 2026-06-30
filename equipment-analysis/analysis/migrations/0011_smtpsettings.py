from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('analysis', '0010_userprofile'),
    ]

    operations = [
        migrations.CreateModel(
            name='SmtpSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email_host', models.CharField(blank=True, max_length=255, verbose_name='SMTP-сервер')),
                ('email_port', models.PositiveIntegerField(default=25, verbose_name='Порт')),
                ('email_use_tls', models.BooleanField(default=False, verbose_name='Использовать TLS')),
                ('email_use_ssl', models.BooleanField(default=False, verbose_name='Использовать SSL')),
                ('email_host_user', models.CharField(blank=True, max_length=255, verbose_name='Логин')),
                ('email_host_password', models.CharField(blank=True, max_length=255, verbose_name='Пароль')),
                ('default_from_email', models.CharField(blank=True, max_length=255, verbose_name='Адрес отправителя')),
            ],
            options={
                'verbose_name': 'Настройки SMTP',
                'verbose_name_plural': 'Настройки SMTP',
            },
        ),
    ]
