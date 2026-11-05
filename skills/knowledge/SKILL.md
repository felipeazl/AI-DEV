---
name: knowledge
description: Queries the active context's knowledge base — what the AiDW has already learned about a system, contract, concept, decision or demand — and answers with the notes and the links between them; also corrects or completes a note when the user asks. Use when the user asks what is known about a project, system or topic, or calls /knowledge.
aidw: admin
---

# knowledge

`aidw.py` lives in `{{root}}` (the AiDW root). Run the commands exactly as `python "{{root}}/aidw.py" ...`, with the
quotes: that is the form the permission rules allow. The user's request is in the message that called this skill.

**Language:** talk to the user in the AiDW UI language (`[ui] language`, shown by `python "{{root}}/aidw.py" show`);
write knowledge notes in the context's language (`language` in its `context.toml`; when absent, the UI language).

## Answer

1. **Find the note:** `python "{{root}}/aidw.py" kb show <topic>` accepts the system key (`system-a`), the note name,
   an alias or the title. With no note of that name, it suggests similar ones; for a subject, use
   `python "{{root}}/aidw.py" kb search <words>` (accents and case do not matter).
2. **Follow the links** only as far as the question needs: `kb show` lists the note's links and who cites it (the
   demands that touched it, the contracts that use it). Open the ones that answer, one level at a time.
3. **Answer briefly:** what the base says, with the path of each note used (a clickable link), and what it does
   **not** say. Give the `atualizado` date when it matters (an old note about code that changes a lot). Do not read
   code to complete the answer unless the user asks; if you do, say what you confirmed and where (`file:line`).
4. If the question comes without a topic ("what do we have?"), show the base's `index.md` summarized: how many notes
   per type and the most cited ones.

## Correct or complete (only when the user asks)

- Follow the base's `README.md`: the fact goes in the note where it lives (do not create another), with the source and
  `atualizado` with today's date; a new note only when none fits, with type, `resumo`, `fontes` and at least one link.
- Then: `python "{{root}}/aidw.py" kb index` and `python "{{root}}/aidw.py" kb check`; fix what it points out.
- Do not commit: `/aidw:done` (or the user) takes the changes to the context's repository. Say which files changed.

## No base

If `kb` answers that the active context has no knowledge base, say so, and that it is enabled with
`[knowledge] dir = "<folder>"` in `context.toml` (conventions in a `README.md` in that folder).
