---
name: debug
description: Diagnose a failure (build, test, runtime or integration error) and decide between retry, a targeted fix, or escalation. Use when any step of a ticket fails.
---

# debug

1. Capture the exact error, command and relevant output.
2. Reproduce it with the smallest command possible.
3. Form a hypothesis and verify it by reading code or adding temporary logging.
4. Fix the root cause, not the symptom. Remove temporary logging.
5. If the cause is outside the ticket scope, or retries reach `max_retries`, stop and report:

```json
{"status": "failed", "error": "...", "cause": "...", "next_action": "CODER_FIX | HUMAN_APPROVAL"}
```
