import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-technic-analysis-key-change-in-production')

DEBUG = True

ALLOWED_HOSTS = ['*']

_replit_domain = os.environ.get('REPLIT_DEV_DOMAIN', '')

CSRF_TRUSTED_ORIGINS = [
    'https://*.replit.dev',
    'https://*.replit.app',
    'https://*.pike.replit.dev',
    'http://localhost',
    'http://localhost:8000',
]

if _replit_domain:
    CSRF_TRUSTED_ORIGINS += [
        f'https://{_replit_domain}',
        f'https://*.{_replit_domain}',
    ]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'analysis',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'technic_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'analysis.context_processors.user_roles',
            ],
        },
    },
]

WSGI_APPLICATION = 'technic_project.wsgi.application'

import dj_database_url as _dj_db_url

_pg_config = _dj_db_url.config(
    default='',
    conn_max_age=600,
    conn_health_checks=True,
)

if _pg_config:
    DATABASES = {'default': _pg_config}
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'Asia/Vladivostok'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = '/login/'

# ── Email / SMTP ───────────────────────────────────────────────────────────────
# Configure these environment variables on the server to enable email alerts.
# Example (Yandex):  EMAIL_HOST=smtp.yandex.ru  EMAIL_PORT=465
#                    EMAIL_HOST_USER=you@yandex.ru  EMAIL_HOST_PASSWORD=apppassword
#                    EMAIL_USE_SSL=True
# Example (Gmail):   EMAIL_HOST=smtp.gmail.com  EMAIL_PORT=587
#                    EMAIL_HOST_USER=you@gmail.com  EMAIL_HOST_PASSWORD=apppassword
#                    EMAIL_USE_TLS=True
# Example (cron):    0 8 * * * /path/to/venv/bin/python /path/to/manage.py send_monitoring_alert
EMAIL_BACKEND   = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST      = os.environ.get('EMAIL_HOST', 'localhost')
EMAIL_PORT      = int(os.environ.get('EMAIL_PORT', '25'))
EMAIL_USE_TLS   = os.environ.get('EMAIL_USE_TLS', '').lower() in ('1', 'true', 'yes')
EMAIL_USE_SSL   = os.environ.get('EMAIL_USE_SSL', '').lower() in ('1', 'true', 'yes')
EMAIL_HOST_USER     = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL  = os.environ.get('DEFAULT_FROM_EMAIL', EMAIL_HOST_USER or 'noreply@example.com')
MONITORING_ALERT_RECIPIENT = os.environ.get('MONITORING_ALERT_RECIPIENT', '5123@goldintercom.ru')
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'

X_FRAME_OPTIONS = 'ALLOWALL'

DATA_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024
