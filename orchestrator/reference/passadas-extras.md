---
when: decidir no plano se a demanda leva passada de bugs e/ou segurança, ou rever essa decisão depois de uma revisão
---

# Specialist passes (on demand)

Each specialist runs **at most once per demand**, and only with a trigger the plan names. Never in a fix
round, never in the short path after delivery (a bug the QA returned, an adjustment asked later).

Call {{agent:bug-hunter}} when at least one applies:
- concurrency, UI thread, timers/polling/retries, async callbacks, state machines or enums with
  many values, transactions/rollback, fragile legacy code — in the part the diff changes, not just nearby;
- a bugfix whose root cause is not obvious (mode `root-cause`, before the plan is final; then it does not run
  again on the diff unless the review finds a CRITICO bug);
- the first review round found a CRITICO bug the reviewer could not explain.

The level alone (`complexa`, `critica`) is not a trigger.

Call {{agent:security}} when at least one applies:
- authentication, authorization, tokens, sessions, OTP, roles/permissions;
- secrets, keys, certificates, cryptography;
- untrusted input reaching SQL, commands, files, HTML, or deserialization; a new or changed
  public endpoint/SOAP method; file upload;
- personal data (documents, e-mail, phone, biometrics) newly stored, logged or returned;
- new or updated dependencies, CORS/TLS/config changes, or a SQL script with grants
  (mode `threat` on the plan when the risk is in the design, `audit` on the diff otherwise).

Skip both for `trivial`/`simples` demands unless a trigger above is explicit.

How to run them cheaply:
- **Once, in parallel with the first review round**, on the same diff file — never every round.
  Tell each one which reviewer IDs already exist so they do not repeat them.
- Their findings (`B<N>-<nn>`, `S<N>-<nn>`) go into the **same triage** as the review (same
  rules for CRITICO/IMPORTANTE/SUGESTAO/doubts) and into the same fix round for the coder.
- Later rounds: no new pass. The reviewer of the fix round checks the specialist's open findings against the
  diff of the fixes (give it their IDs and the report path).
- Their `state` is `audit_*`: `RETURN` to the step that called them (review triage, or the plan
  when used in `threat`/`root-cause` mode).
