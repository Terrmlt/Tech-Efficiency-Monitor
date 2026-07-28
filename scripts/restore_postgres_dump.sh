#!/usr/bin/env bash
set -euo pipefail

# Restore a plain-text PostgreSQL pg_dump into the database used by Django.
# Usage: DATABASE_URL=... ./scripts/restore_postgres_dump.sh [dump-file]
dump_file="${1:-dump13072026.json}"

if [[ ! -f "$dump_file" ]]; then
  echo "Dump file not found: $dump_file" >&2
  exit 1
fi
if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL must point to the PostgreSQL database used by Django." >&2
  exit 1
fi
if ! grep -qE '^(-- PostgreSQL database dump|CREATE TABLE |COPY )' "$dump_file"; then
  echo "The file does not look like a plain-text PostgreSQL dump: $dump_file" >&2
  exit 1
fi

echo "Restoring $dump_file into the database from DATABASE_URL..."
{
  printf '%s\n' 'DROP SCHEMA public CASCADE;' 'CREATE SCHEMA public;'
  cat "$dump_file"
} | psql "$DATABASE_URL" --set ON_ERROR_STOP=1 --single-transaction >/dev/null

echo "Restore complete. Record counts:"
psql "$DATABASE_URL" --set ON_ERROR_STOP=1 -Atc "
  SELECT 'users=' || count(*) FROM auth_user;
  SELECT 'sections=' || count(*) FROM analysis_section;
  SELECT 'reports=' || count(*) FROM analysis_report;
  SELECT 'vehicle_records=' || count(*) FROM analysis_vehiclerecord;
"