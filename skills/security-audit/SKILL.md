---
name: security-audit
description: Audit a diff, code area or plan for exploitable vulnerabilities (injection, authn/authz, secrets, crypto, data exposure, input validation, dependencies, configuration), each with a concrete attack path. Use when the Security agent receives an audit or threat task.
---

# security-audit

Goal: exploitable weaknesses, ranked by impact. Generic advice ("consider validating input")
without an attack path is noise.

## audit (diff or area)

1. Map the **attack surface** the change touches: entry points (endpoints, SOAP methods, UI
   fields, files read, queue messages, command-line/process calls), the data that flows in, the
   trust boundary it crosses, and the sensitive assets reached (credentials, keys, personal
   data, money/state changes).
2. Follow each untrusted input to every sink it reaches. Check the categories below.
3. For each candidate, write the **attack path**: who (anonymous, authenticated user, another
   tenant/partner, local user), the input, and what they gain. If the path needs a condition
   you cannot confirm in the code, it is a doubt.
4. Rank: CRITICO (remote exploit, auth bypass, secret/key exposure, personal data leak at scale,
   injection), IMPORTANTE (exploitable with preconditions, missing authorization on a sensitive
   action, weak crypto on sensitive data), SUGESTAO (hardening, defense in depth).

### Categories

- **Injection:** SQL (string concatenation vs parameters/query builder), command/process
  arguments, LDAP/XPath, path traversal in file names, HTML/JS output (XSS), deserialization of
  untrusted data, XML external entities.
- **Authentication:** token validation (signature, expiry, audience), fixed/default
  credentials, OTP brute force and reuse, session fixation.
- **Authorization:** every sensitive action checks **who** may do it, on **which** record
  (IDOR: id from the request used without ownership check), role checks that always return
  true, client-side-only checks.
- **Secrets:** hardcoded keys, tokens or connection strings; secrets in logs, exceptions,
  responses, URLs, commits or config files; secrets compared with non-constant-time equality.
- **Crypto:** algorithm and mode, IV/nonce reuse or derived from the key, key size, randomness
  source, certificate validation disabled, private keys handled or persisted in clear.
- **Data exposure:** personal data (documents, e-mail, phone, biometrics) in logs, responses or
  errors beyond need; stack traces to the client; verbose error messages.
- **Input validation:** size limits, type/format checks on the server, upload type and size.
- **Dependencies and config:** new/updated packages with known vulnerabilities, CORS, TLS,
  debug flags, permissive defaults, secrets in `appsettings`.

## threat (plan, before implementation)

List the assets, entry points and trust boundaries of the planned change; for each relevant
category above, the threat and the **control the plan must include** (as an acceptance
criterion or task). Findings use the same format; `fix` is the change to the plan.

## Report (Markdown, the path the task gives)

Identification (scope, mode, round) · Attack surface (entry points, data, boundaries) ·
Findings (`S<round>-<nn>`: what / attack path / evidence / suggested fix / pre-existing or
introduced) · Doubts · Categories checked without findings (one line each) · Summary table by
severity.

**Round ≥ 2:** only your open findings and the diff of the fixes: `fixed` / `not_fixed` with
evidence, and whether the fix opened a new path.
