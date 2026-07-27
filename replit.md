# Анализ эффективности техники

Django-приложение для загрузки и анализа Excel-отчётов по работе техники (формат Омником).

## Run & Operate

- Запускается через workflow "Start application": `pip install -r equipment-analysis/requirements.txt -q && cd equipment-analysis && python3 manage.py migrate --run-syncdb && python3 manage.py runserver 0.0.0.0:5000`
- Приложение слушает порт 5000 (требование Replit preview)
- `cd equipment-analysis && python3 manage.py migrate` — применить миграции БД
- `cd equipment-analysis && python3 manage.py makemigrations analysis` — создать миграции после изменений моделей
- В базе загружены данные из `dump13072026.json` (pg_dump от 13.07.2026) через `psql`: 6 пользователей, 27 отчётов, 1156 записей по ТС

## Stack

- Python 3.11 + Django 5.x
- PostgreSQL (база данных Replit, подключение через `DATABASE_URL` и `dj-database-url`; падает обратно на SQLite `db.sqlite3`, если `DATABASE_URL` не задан)
- openpyxl (чтение Excel)
- Bootstrap 5 (UI)

## Where things live

- `equipment-analysis/` — Django-проект
- `equipment-analysis/analysis/` — основное приложение
- `equipment-analysis/analysis/utils.py` — парсинг Excel, обнаружение аномалий, расчёт метрик
- `equipment-analysis/analysis/models.py` — модели Report и VehicleRecord
- `equipment-analysis/analysis/templates/analysis/` — HTML-шаблоны
- `equipment-analysis/dump.json` — дамп исходных данных проекта (загружен в БД)

## Architecture decisions

- Нормативы хранятся в модели Report (отдельно для каждого отчёта), не глобально
- Колонки "% от периода отчета" пропускаются при парсинге (F, H, J, N)
- Аномалии фиксируются, но не исключаются из расчётов (выводятся с пометкой)
- Расчёт эффективности типа зависит от группы ТС

## Product

- Загрузка Excel-файла (формат Ежемесячный отчёт Омником)
- Настройка нормативных показателей (часы/сутки, % холостого хода, % простоя, % без движения)
- Автоматическое обнаружение аномалий (отрицательный расход, работа без топлива и т.д.)
- Расчёт метрик: расход к норме, выход техники, эффективность по типу
- Сводная таблица по группам техники
- Фильтрация по группе и наличию аномалий

## Формулы расчёта

1. **Расход к норме** = фактический расход ÷ время работы (ч) ÷ норму расхода × 100%
2. **Выход техники** = время работы (ч) ÷ норму/сутки × 100%
3. **Эффективность бульдозеры/погрузчики** = % холостого хода ÷ норму % × 100%
4. **Эффективность экскаваторы** = % времени простоя стрелы ÷ норму % × 100%
5. **Эффективность самосвалы** = % без движения ÷ норму % × 100%

## User preferences

_Populate as you build — explicit user instructions worth remembering across sessions._

## Gotchas

- При парсинге времена приходят как datetime.timedelta (уже разобранные openpyxl) или как строки "чч:мм:сс" — оба формата обрабатываются
- Значение '-' в полях времени или расхода = данные отсутствуют
- Норма расхода (л/ч) уже есть в файле (колонка K); норма выхода — настраивается пользователем
