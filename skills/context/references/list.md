# context list

1. Run `python "{{root}}/aidw.py" context list` ({{root}} is the AiDW root) — exactly in this form, with the quotes: it is the one the permission rules allow without asking for approval.
2. Show the user, in a short table: name, description, whether it is **active** (`*`), repository (its own git, the
   remote only by host — never show the full URL), systems and whether the plugin is installed.
3. Point out what deserves attention, if any: a context without its own git repository, a context without a remote
   (its content exists only on this machine), an error in `context.toml`.
4. Finish with the possible next step: `/aidw:context use <name>` to switch, `/aidw:context create` for a new one.

Change nothing: this skill only reads. Talk to the user in the AiDW UI language (`[ui] language`, shown by
`python "{{root}}/aidw.py" show`).
