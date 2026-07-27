#!/usr/bin/env bash
# Restore the PostgreSQL database from a pg_dump SQL file.
# Usage: bash scripts/restore_db.sh [path/to/dump.sql]
#
# Default dump: dump13072026.json (pg_dump от 13.07.2026)
# The file has a .json extension but is a standard pg_dump plain-text SQL dump.
#
# Prerequisites: PGHOST, PGPORT, PGUSER, PGDATABASE env vars must be set
# (Replit sets them automatically when postgresql-16 module is active).

set -euo pipefail

DUMP_FILE="${1:-dump13072026.json}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
DUMP_PATH="$REPO_ROOT/$DUMP_FILE"

if [ ! -f "$DUMP_PATH" ]; then
  echo "ERROR: dump file not found: $DUMP_PATH"
  exit 1
fi

echo "==> Dropping existing tables in public schema..."
psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -c "
DO \$\$ DECLARE
  r RECORD;
BEGIN
  FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
    EXECUTE 'DROP TABLE IF EXISTS public.' || quote_ident(r.tablename) || ' CASCADE';
  END LOOP;
END \$\$;
"

echo "==> Restoring from $DUMP_PATH ..."
psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -f "$DUMP_PATH"

echo "==> Applying any pending Django migrations..."
cd "$REPO_ROOT/equipment-analysis"
python3 manage.py migrate --run-syncdb

echo "==> Verification:"
psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -c "
SELECT 'auth_user'                 AS table_name, COUNT(*) AS rows FROM auth_user
UNION ALL
SELECT 'analysis_section',                        COUNT(*) FROM analysis_section
UNION ALL
SELECT 'analysis_report',                         COUNT(*) FROM analysis_report
UNION ALL
SELECT 'analysis_vehiclerecord',                  COUNT(*) FROM analysis_vehiclerecord
UNION ALL
SELECT 'analysis_monitoringvehicle',              COUNT(*) FROM analysis_monitoringvehicle
UNION ALL
SELECT 'analysis_monitoringrecord',               COUNT(*) FROM analysis_monitoringrecord;
"

echo "==> Done. Database restored from $DUMP_FILE."
