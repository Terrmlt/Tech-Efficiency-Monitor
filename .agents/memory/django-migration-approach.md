---
name: Django migration approach in Replit
description: How to apply Django migrations when manage.py migrate hangs in the Replit environment
---

## The Rule
When `python manage.py migrate` (or `makemigrations`) hangs indefinitely, apply schema changes directly to the SQLite database via a standalone Python script using the built-in `sqlite3` module, then register the migration in the `django_migrations` table manually.

**Why:** In this Replit environment, running a second Django process while the StatReloader-based dev server is running causes the new process to hang during Django setup. The exact cause is unclear (possibly inotify fd exhaustion or a process-group scheduling issue), but it is reproducible — `makemigrations`, `migrate`, and even `python -c "import django; django.setup()"` all block indefinitely.

**How to apply:**
1. Write a standalone script (e.g., `apply_migration.py`) that:
   - Opens `db.sqlite3` via `sqlite3.connect(path, timeout=30)`
   - Checks `django_migrations` to skip if already applied
   - Runs the raw `ALTER TABLE` / `CREATE TABLE` DDL statements
   - Inserts a row into `django_migrations` to register the migration
2. Run the script via bash: `python apply_migration.py`
3. Delete the script after use
4. Restart the workflow — Django will see the migration as already applied and start cleanly

**Note:** `configureWorkflow` in `code_execution` also fails (CANCEL error) in this environment, so `.replit` workflow commands cannot be changed programmatically — they must be edited by the user if a permanent `migrate` step is needed in the startup command.

**Update (equipment-analysis project):** in that project the hang was actually caused by running `manage.py migrate` concurrently with a live `runserver` process (both racing on the DB), not by SQLite itself — the project actually uses Postgres via `DATABASE_URL`/`dj-database-url`, falling back to SQLite only if unset. Fix was simply: kill any running server/migrate process first, then run `migrate --run-syncdb` standalone. No manual DDL/sqlite3 script was needed once the conflicting process was gone. Try this simpler fix first before resorting to the manual DDL script.
