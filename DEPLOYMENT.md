# Инструкция по развёртыванию на Linux-сервере

## Восстановление базы из PostgreSQL-дампа

Файл `dump13072026.json` — это plain-text дамп PostgreSQL (расширение
исторически указано неверно), а не JSON-файл Django. Для восстановления
используйте PostgreSQL `DATABASE_URL` приложения:

```bash
DATABASE_URL='postgresql://...' ./scripts/restore_postgres_dump.sh dump13072026.json
```

Скрипт проверяет формат файла, заменяет схему `public` и после восстановления
выводит контрольные количества пользователей, отчётов и записей техники.
Перед запуском убедитесь, что выбранная база не содержит нужные данные:
существующая схема `public` будет удалена.

> Версия стека: Python 3.11 · Django 5.x · SQLite / PostgreSQL  
> Инструмент подключения: PuTTY (SSH)

---

## Содержание

1. [Требования к серверу](#1-требования-к-серверу)
2. [Подключение через PuTTY](#2-подключение-через-putty)
3. [Установка зависимостей системы](#3-установка-зависимостей-системы)
4. [Размещение кода на сервере](#4-размещение-кода-на-сервере)
   - [Вариант А — через GitHub (рекомендуется)](#вариант-а--через-github-рекомендуется)
   - [Вариант Б — копирование файлов через SFTP/WinSCP](#вариант-б--копирование-файлов-через-sftpwinscp)
5. [Настройка Python-окружения](#5-настройка-python-окружения)
6. [Переменные окружения и настройки](#6-переменные-окружения-и-настройки)
7. [Выбор базы данных](#7-выбор-базы-данных)
   - [SQLite (простой вариант)](#sqlite-простой-вариант)
   - [PostgreSQL (для production)](#postgresql-для-production)
8. [Применение миграций и сбор статики](#8-применение-миграций-и-сбор-статики)
9. [Создание администратора](#9-создание-администратора)
10. [Запуск приложения через Gunicorn + systemd](#10-запуск-приложения-через-gunicorn--systemd)
11. [Настройка Nginx (обратный прокси)](#11-настройка-nginx-обратный-прокси)
12. [Обновление приложения без потери данных](#12-обновление-приложения-без-потери-данных)
13. [Резервное копирование базы данных](#13-резервное-копирование-базы-данных)
14. [Работа с GitHub](#14-работа-с-github)
15. [Частые ошибки и их решения](#15-частые-ошибки-и-их-решения)

---

## 1. Требования к серверу

| Параметр | Минимум | Рекомендуется |
|----------|---------|---------------|
| ОС | Ubuntu 20.04 / Debian 11 | Ubuntu 22.04 LTS |
| CPU | 1 ядро | 2 ядра |
| RAM | 512 МБ | 1 ГБ |
| Диск | 5 ГБ | 20 ГБ |
| Порт | 22 (SSH) открыт | 22, 80, 443 |

Приложение работает на **Python 3.11**. Убедитесь что сервер имеет доступ в интернет (для установки пакетов).

---

## 2. Подключение через PuTTY

1. Скачайте PuTTY: https://www.putty.org/
2. Откройте PuTTY, введите:
   - **Host Name**: IP-адрес или домен вашего сервера
   - **Port**: 22
   - **Connection type**: SSH
3. Нажмите **Open** → введите логин и пароль.

> **Совет:** Чтобы не вводить пароль каждый раз, настройте SSH-ключ:  
> В PuTTY → Connection → SSH → Auth → укажите файл `.ppk`.

**Полезные настройки PuTTY:**
- Session → Logging → включите лог сессии (удобно при ошибках)
- Terminal → Keyboard → The Backspace key: Control-H
- Connection → keepalives: 60 секунд (чтобы сессия не обрывалась)

---

## 3. Установка зависимостей системы

```bash
# Обновление пакетов
sudo apt update && sudo apt upgrade -y

# Python 3.11 и pip
sudo apt install -y python3.11 python3.11-venv python3.11-dev python3-pip

# Дополнительные инструменты
sudo apt install -y git nginx curl build-essential

# Для PostgreSQL (если планируете использовать PostgreSQL)
sudo apt install -y postgresql postgresql-contrib libpq-dev
```

Проверьте версию Python:
```bash
python3.11 --version
# Ожидаемый вывод: Python 3.11.x
```

---

## 4. Размещение кода на сервере

### Вариант А — через GitHub (рекомендуется)

**Шаг 1.** Создайте репозиторий на GitHub (https://github.com/new).

**Шаг 2.** Загрузите код из Replit в репозиторий:

В Replit откройте терминал и выполните:
```bash
cd /home/runner/workspace
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/ВАШ_ЛОГИН/ВАШ_РЕПОЗИТОРИЙ.git
git push -u origin main
```

**Шаг 3.** На сервере (в PuTTY):
```bash
# Создайте директорию для приложения
sudo mkdir -p /var/www/technic
sudo chown $USER:$USER /var/www/technic

# Клонируйте репозиторий
git clone https://github.com/ВАШ_ЛОГИН/ВАШ_РЕПОЗИТОРИЙ.git /var/www/technic
cd /var/www/technic
```

Если репозиторий приватный, потребуется токен доступа (Personal Access Token):
```bash
git clone https://ВАШ_ТОКЕН@github.com/ВАШ_ЛОГИН/ВАШ_РЕПОЗИТОРИЙ.git /var/www/technic
```
Токен создаётся на GitHub: Settings → Developer settings → Personal access tokens → Generate new token.

### Вариант Б — копирование файлов через SFTP/WinSCP

1. Скачайте WinSCP: https://winscp.net/
2. Подключитесь (те же IP / логин / пароль что в PuTTY)
3. Скопируйте папку `equipment-analysis/` и файл `requirements.txt` на сервер в `/var/www/technic/`

---

## 5. Настройка Python-окружения

```bash
cd /var/www/technic

# Создайте виртуальное окружение
python3.11 -m venv venv

# Активируйте его
source venv/bin/activate

# Обновите pip
pip install --upgrade pip

# Установите зависимости проекта
pip install -r equipment-analysis/requirements.txt

# Дополнительно установите gunicorn (WSGI-сервер для production)
pip install gunicorn
```

> **Важно:** Всегда активируйте venv перед любыми командами Django:  
> `source /var/www/technic/venv/bin/activate`

---

## 6. Переменные окружения и настройки

Создайте файл с переменными окружения (он не попадает в git):

```bash
nano /var/www/technic/.env
```

Содержимое файла `.env`:
```
# Обязательно: секретный ключ (замените на случайную строку из 50+ символов)
DJANGO_SECRET_KEY=замените-это-своим-длинным-случайным-ключом-минимум-50-символов

# Для PostgreSQL (если используете PostgreSQL, иначе не указывайте)
# DATABASE_URL=postgresql://пользователь:пароль@localhost:5432/имя_базы

# Для SQLite — DATABASE_URL не указывайте (будет использоваться автоматически)
```

Сгенерировать безопасный SECRET_KEY:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

Настройте `settings.py` для production — откройте файл:
```bash
nano /var/www/technic/equipment-analysis/technic_project/settings.py
```

Измените следующие строки:
```python
# Было:
DEBUG = True

# Станет:
DEBUG = os.environ.get('DEBUG', 'False') == 'True'

# Добавьте ваш домен или IP в ALLOWED_HOSTS:
ALLOWED_HOSTS = ['ВАШ_IP', 'ваш-домен.ru', 'localhost']

# Добавьте ваш домен в CSRF_TRUSTED_ORIGINS:
CSRF_TRUSTED_ORIGINS = [
    'http://ВАШ_IP',
    'https://ваш-домен.ru',
    'http://localhost',
]
```

---

## 7. Выбор базы данных

### SQLite (простой вариант)

SQLite используется **по умолчанию** если переменная `DATABASE_URL` не задана.  
База данных хранится в файле: `equipment-analysis/db.sqlite3`

**Плюсы:** не требует отдельной установки, просто файл на диске.  
**Минусы:** не подходит для нескольких одновременных пользователей.

**Резервная копия SQLite:**
```bash
cp /var/www/technic/equipment-analysis/db.sqlite3 /var/backups/db_$(date +%Y%m%d_%H%M%S).sqlite3
```

### PostgreSQL (для production)

Используйте PostgreSQL если планируется несколько пользователей одновременно.

```bash
# Создайте пользователя и базу данных
sudo -u postgres psql

# Внутри psql:
CREATE USER technic_user WITH PASSWORD 'ваш_пароль';
CREATE DATABASE technic_db OWNER technic_user;
GRANT ALL PRIVILEGES ON DATABASE technic_db TO technic_user;
\q
```

В файл `.env` добавьте:
```
DATABASE_URL=postgresql://technic_user:ваш_пароль@localhost:5432/technic_db
```

---

## 8. Применение миграций и сбор статики

```bash
cd /var/www/technic
source venv/bin/activate

# Загрузите переменные окружения из .env
export $(cat .env | grep -v '#' | xargs)

# Перейдите в папку Django-проекта
cd equipment-analysis

# Примените все миграции (создаёт структуру БД)
python manage.py migrate

# Соберите статические файлы (CSS, JS) в одну папку
python manage.py collectstatic --noinput
```

После `migrate` вы увидите список применённых миграций — это нормально.  
Команда `collectstatic` создаст папку `staticfiles/`.

---

## 9. Создание администратора

```bash
cd /var/www/technic/equipment-analysis
source ../venv/bin/activate
export $(cat ../.env | grep -v '#' | xargs)

python manage.py createsuperuser
```

Введите: имя пользователя, email (можно пропустить Enter), пароль дважды.

---

## 10. Запуск приложения через Gunicorn + systemd

Gunicorn — это production WSGI-сервер. systemd — менеджер служб Linux, который автоматически запускает приложение при старте сервера и перезапускает при сбоях.

**Создайте systemd-юнит:**
```bash
sudo nano /etc/systemd/system/technic.service
```

Содержимое файла:
```ini
[Unit]
Description=Technic Analysis Django Application
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/technic/equipment-analysis
EnvironmentFile=/var/www/technic/.env
ExecStart=/var/www/technic/venv/bin/gunicorn \
    --workers 3 \
    --bind 127.0.0.1:8000 \
    --timeout 120 \
    --access-logfile /var/log/technic/access.log \
    --error-logfile /var/log/technic/error.log \
    technic_project.wsgi:application
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

> Замените `www-data` на вашего пользователя Linux если нужно.  
> Число `--workers 3` = 2 × кол-во_ядер + 1. Для 1 ядра: 3.

Создайте папку для логов и установите права:
```bash
sudo mkdir -p /var/log/technic
sudo chown www-data:www-data /var/log/technic
sudo chown -R www-data:www-data /var/www/technic
```

Запустите и включите автозапуск:
```bash
sudo systemctl daemon-reload
sudo systemctl start technic
sudo systemctl enable technic

# Проверьте статус
sudo systemctl status technic
```

Если всё в порядке, вы увидите `Active: active (running)`.

---

## 11. Настройка Nginx (обратный прокси)

Nginx принимает запросы из интернета и передаёт их Gunicorn.

```bash
sudo nano /etc/nginx/sites-available/technic
```

Содержимое файла:
```nginx
server {
    listen 80;
    server_name ВАШ_IP ваш-домен.ru;

    client_max_body_size 25M;

    location /static/ {
        alias /var/www/technic/equipment-analysis/staticfiles/;
        expires 30d;
    }

    location /media/ {
        alias /var/www/technic/equipment-analysis/media/;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
```

Включите конфигурацию:
```bash
sudo ln -s /etc/nginx/sites-available/technic /etc/nginx/sites-enabled/
sudo nginx -t          # Проверка конфигурации (должно быть "test is successful")
sudo systemctl restart nginx
sudo systemctl enable nginx
```

Откройте в браузере `http://ВАШ_IP` — должна открыться страница входа.

---

## 12. Обновление приложения без потери данных

> **Главное правило:** миграции всегда применяются ПОСЛЕ обновления кода.  
> База данных никогда не удаляется при обновлении.

### Если используете GitHub (рекомендуется):

```bash
cd /var/www/technic

# 1. Сделайте резервную копию базы данных (ВСЕГДА перед обновлением)
cp equipment-analysis/db.sqlite3 /var/backups/db_before_update_$(date +%Y%m%d_%H%M%S).sqlite3
# Или для PostgreSQL:
# sudo -u postgres pg_dump technic_db > /var/backups/db_before_update_$(date +%Y%m%d_%H%M%S).sql

# 2. Получите новый код из GitHub
git pull origin main

# 3. Активируйте виртуальное окружение
source venv/bin/activate
export $(cat .env | grep -v '#' | xargs)

# 4. Установите новые зависимости (если они появились)
pip install -r equipment-analysis/requirements.txt

# 5. Примените новые миграции (безопасно — изменяет структуру БД без удаления данных)
cd equipment-analysis
python manage.py migrate

# 6. Обновите статику
python manage.py collectstatic --noinput

# 7. Перезапустите приложение
cd ..
sudo systemctl restart technic

# 8. Проверьте что всё работает
sudo systemctl status technic
```

### Если загружаете файлы вручную (WinSCP):

1. Сделайте резервную копию базы данных (шаг 1 выше)
2. Скопируйте новые файлы (перезаписав старые), **не трогая** `db.sqlite3` и `.env`
3. Выполните шаги 3–8 выше

### Откат к предыдущей версии при ошибке:

```bash
# Если что-то пошло не так — откатите код
git log --oneline -5         # Посмотрите список коммитов
git checkout ХЭШ_КОММИТА .  # Откатите к нужному коммиту

# Восстановите базу из резервной копии
cp /var/backups/db_before_update_ДАТА.sqlite3 equipment-analysis/db.sqlite3

# Перезапустите
sudo systemctl restart technic
```

---

## 13. Резервное копирование базы данных

Настройте автоматическое резервное копирование через cron.

```bash
# Создайте скрипт резервного копирования
sudo nano /usr/local/bin/technic_backup.sh
```

Содержимое скрипта:
```bash
#!/bin/bash
BACKUP_DIR=/var/backups/technic
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

# SQLite:
cp /var/www/technic/equipment-analysis/db.sqlite3 $BACKUP_DIR/db_$DATE.sqlite3

# PostgreSQL (раскомментируйте если используете PostgreSQL):
# sudo -u postgres pg_dump technic_db > $BACKUP_DIR/db_$DATE.sql

# Удалить копии старше 30 дней
find $BACKUP_DIR -name "db_*.sqlite3" -mtime +30 -delete

echo "Backup completed: $BACKUP_DIR/db_$DATE.sqlite3"
```

```bash
sudo chmod +x /usr/local/bin/technic_backup.sh

# Запуск резервного копирования каждый день в 3:00
crontab -e
```

Добавьте в конец файла:
```
0 3 * * * /usr/local/bin/technic_backup.sh >> /var/log/technic_backup.log 2>&1
```

---

## 14. Работа с GitHub

**Да, GitHub можно и нужно использовать для обновлений!** Это самый удобный способ.

### Первичная настройка репозитория на Replit:

```bash
# В терминале Replit
git config --global user.email "ваш@email.com"
git config --global user.name "Ваше Имя"
git remote add origin https://github.com/ВАШ_ЛОГИН/ВАШ_РЕПОЗИТОРИЙ.git
```

### Публикация изменений из Replit на GitHub:

```bash
git add .
git commit -m "Описание изменений"
git push origin main
```

### Получение обновлений на сервере:

```bash
cd /var/www/technic
git pull origin main
```

### Что НЕ должно попасть в GitHub (создайте `.gitignore`):

Файл `.gitignore` в корне проекта должен содержать:
```
# База данных
*.sqlite3

# Переменные окружения
.env
*.env

# Python
__pycache__/
*.pyc
*.pyo
venv/
.venv/

# Django
staticfiles/
media/
*.log

# Replit
.replit
replit.nix
.local/
```

> Таким образом база данных и секреты **никогда не попадут в GitHub**.

### Схема работы через GitHub:

```
Replit (разработка)
       │
       │  git push
       ▼
   GitHub (хранилище кода)
       │
       │  git pull
       ▼
Linux-сервер (production)
```

---

## 15. Частые ошибки и их решения

---

### ❌ `ModuleNotFoundError: No module named 'django'`

**Причина:** Виртуальное окружение не активировано.  
**Решение:**
```bash
source /var/www/technic/venv/bin/activate
```

---

### ❌ `django.db.utils.OperationalError: no such table: ...`

**Причина:** Миграции не были применены.  
**Решение:**
```bash
cd /var/www/technic/equipment-analysis
python manage.py migrate
```

---

### ❌ `DisallowedHost at /` или `Invalid HTTP_HOST header`

**Причина:** IP или домен сервера не добавлен в `ALLOWED_HOSTS`.  
**Решение:** В `settings.py`:
```python
ALLOWED_HOSTS = ['ВАШ_IP', 'ваш-домен.ru', 'www.ваш-домен.ru']
```

---

### ❌ `CSRF verification failed` (при отправке форм)

**Причина:** Ваш домен не в `CSRF_TRUSTED_ORIGINS`.  
**Решение:** В `settings.py`:
```python
CSRF_TRUSTED_ORIGINS = ['http://ВАШ_IP', 'https://ваш-домен.ru']
```

---

### ❌ `502 Bad Gateway` в Nginx

**Причина:** Gunicorn не запущен или упал.  
**Решение:**
```bash
sudo systemctl status technic          # Посмотреть статус
sudo journalctl -u technic -n 50       # Посмотреть последние ошибки
sudo systemctl restart technic         # Перезапустить
```

---

### ❌ `PermissionError: [Errno 13] Permission denied: 'db.sqlite3'`

**Причина:** Gunicorn запущен от другого пользователя, чем владелец файла.  
**Решение:**
```bash
sudo chown -R www-data:www-data /var/www/technic
sudo chmod 664 /var/www/technic/equipment-analysis/db.sqlite3
```

---

### ❌ Статика (CSS/JS) не загружается — страница без оформления

**Причина:** Не выполнен `collectstatic` или Nginx не настроен на папку `staticfiles`.  
**Решение:**
```bash
python manage.py collectstatic --noinput
sudo systemctl restart nginx
```

---

### ❌ `django.core.exceptions.ImproperlyConfigured: The SECRET_KEY setting must not be empty`

**Причина:** Переменная `DJANGO_SECRET_KEY` не задана.  
**Решение:** Добавьте в `.env`:
```
DJANGO_SECRET_KEY=ваш-длинный-случайный-ключ
```
И убедитесь что `.env` загружается:
```bash
export $(cat /var/www/technic/.env | grep -v '#' | xargs)
```

---

### ❌ Ошибка при `git pull` — `error: Your local changes...`

**Причина:** На сервере вручную изменили файлы, которые теперь конфликтуют с GitHub.  
**Решение:**
```bash
git stash          # Временно сохранить локальные изменения
git pull           # Получить обновления
git stash pop      # Вернуть локальные изменения (или git stash drop — выбросить)
```

---

### ❌ `413 Request Entity Too Large` при загрузке Excel-файла

**Причина:** Nginx ограничивает размер загружаемых файлов.  
**Решение:** В конфигурации Nginx добавьте:
```nginx
client_max_body_size 25M;
```
Затем: `sudo systemctl restart nginx`

---

### ❌ `psycopg2.OperationalError: could not connect to server`

**Причина:** PostgreSQL не запущен или неверные параметры подключения в `DATABASE_URL`.  
**Решение:**
```bash
sudo systemctl status postgresql       # Проверить статус
sudo systemctl start postgresql        # Запустить если остановлен
# Проверьте DATABASE_URL в файле .env
```

---

### ❌ PuTTY: `Connection timed out` или `Network error: Connection refused`

**Причина:** Неверный IP, порт SSH закрыт, или сервер недоступен.  
**Решение:**
- Проверьте IP сервера в панели управления хостингом
- Убедитесь что порт 22 открыт в firewall: `sudo ufw allow 22`
- Попробуйте пинговать сервер из командной строки Windows: `ping ВАШ_IP`

---

### ❌ После обновления данные исчезли

**Причина:** Возможно была выполнена команда `migrate --run-syncdb` или случайно удалён файл `db.sqlite3`.  
**Решение:** Восстановите из резервной копии:
```bash
cp /var/backups/technic/db_ДАТА.sqlite3 /var/www/technic/equipment-analysis/db.sqlite3
sudo systemctl restart technic
```

> **Важно:** Команды `python manage.py flush` и `python manage.py migrate --fake-initial` и удаление папки миграций — опасны и могут привести к потере данных. Никогда не выполняйте их в production без резервной копии.

---

## Краткая шпаргалка команд

```bash
# Активировать окружение
source /var/www/technic/venv/bin/activate

# Перейти в папку проекта
cd /var/www/technic/equipment-analysis

# Загрузить переменные окружения
export $(cat /var/www/technic/.env | grep -v '#' | xargs)

# Применить миграции
python manage.py migrate

# Собрать статику
python manage.py collectstatic --noinput

# Перезапустить приложение
sudo systemctl restart technic

# Посмотреть логи приложения
sudo journalctl -u technic -f

# Посмотреть логи Nginx
sudo tail -f /var/log/nginx/error.log

# Резервная копия БД (SQLite)
cp db.sqlite3 /var/backups/technic/db_$(date +%Y%m%d_%H%M%S).sqlite3

# Обновление из GitHub
git pull origin main && pip install -r requirements.txt && python manage.py migrate && python manage.py collectstatic --noinput && sudo systemctl restart technic
```
