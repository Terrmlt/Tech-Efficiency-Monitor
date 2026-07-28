---
name: Imported database dumps
description: Identifies and restores imported database backups whose file extensions do not match their actual format.
---

Imported backups may have misleading extensions. Inspect the first lines and format before choosing a restore command; a PostgreSQL plain-text `pg_dump` can be restored through `psql` even when named `.json`.

**Why:** A received file named `.json` was actually a PostgreSQL dump and could not be parsed as JSON.

**How to apply:** Check for PostgreSQL dump markers such as `CREATE TABLE` and `COPY` before using Django fixtures or JSON parsing.