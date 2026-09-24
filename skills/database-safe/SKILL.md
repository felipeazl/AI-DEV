---
name: database-safe
description: Classify and gate database operations before execution according to the database policy. Use before running any SQL, migration or data change.
---

# database-safe

1. Identify the environment (dev, staging, production). Unknown means production.
2. Classify every statement:
   - `read` — SELECT without side effects.
   - `write` — INSERT/UPDATE/DELETE. Estimate affected rows first with a SELECT COUNT.
   - `ddl` — CREATE/ALTER/DROP/TRUNCATE, migrations, permission changes.
3. Require `HUMAN_APPROVAL` for: any production write or DDL, DROP, TRUNCATE, destructive
   migrations, updates/deletes without a WHERE clause or affecting many rows, GRANT/REVOKE.
4. Prefer transactions and a tested rollback for writes.
5. Never print connection strings or credentials.
