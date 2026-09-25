---
name: database-safe
description: Classify and gate every database operation before it runs — reads only through the allowed validator, every write proposed for human approval with the exact statement, check query and rollback. Use before running any SQL, migration or data change.
---

# database-safe

The active policies win whenever they are stricter than this skill (e.g. "every write in any
environment needs approval"). This skill never relaxes a policy.

1. **Environment.** Name it (dev, qa, staging/hml, production). Unknown = production. Production
   and any environment the policies forbid: stop, report, do not run anything.
2. **Classify** every statement:
   - `read` — `SELECT` without side effects.
   - `write` — `INSERT` / `UPDATE` / `DELETE` / `MERGE`, stored procedures that change data.
   - `ddl` — `CREATE` / `ALTER` / `DROP` / `TRUNCATE`, migrations, `GRANT` / `REVOKE`.
   A batch with any write is a write. When unsure, treat it as a write.
3. **Reads** run only through the read-only tool the active context names (e.g. a validator
   script that rejects non-`SELECT` and runs inside a rollback) — never through a raw client.
   Select only the columns you need and limit rows (`TOP`).
4. **Writes and DDL are never executed on your own.** Propose them and return
   `state: "policy_requires_approval"` with, for each statement:
   - environment and database;
   - the exact statement — one statement per proposal, `WHERE` on the key, never a mass update;
   - the `SELECT` that shows the current value and the rows affected (run it first, as a read);
   - the previous value saved in the report, and the statement that reverts it.
   Execute only when re-invoked with that exact statement approved, then run the check `SELECT`
   again and report before/after.
5. **Scripts in the repository** (`.sql` files) are code, not execution: write them following
   the project's conventions; running them is a write (step 4).
6. Never print connection strings, passwords or tokens — refer to them by variable name.
