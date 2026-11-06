# context use

`aidw.py` lives in `{{root}}` (the AiDW root). Run the commands exactly as `python "{{root}}/aidw.py" ...`, with the quotes: that is the form the permission rules allow. Talk to the user in the AiDW UI language (`[ui] language`, shown by `python "{{root}}/aidw.py" show`).

1. **Which context:** what the user asked for. If they did not say or the name does not match, run
   `python "{{root}}/aidw.py" context list` and ask with the options (empty = no context).
2. **Open demand:** run `python "{{root}}/aidw.py" demand list --active`. If there is an active demand in the current
   context, warn that it will be paused (the rules and the agents change) and ask whether to switch anyway.
3. **Validate:** `python "{{root}}/aidw.py" context check <name>`. On error, show the errors and stop — do not switch
   to a broken context. Warnings: show them and continue.
4. **Switch:** `python "{{root}}/aidw.py" context use <name>`. It writes only the `active` line of `aidw.config.toml`
   (the comments stay), runs `apply` and, if the AiDW is installed, `install`: the `aidw` plugin (same name, same
   commands) gets the new context's agents, systems and policies, and the old context's global rules leave while the
   new one's come in.
5. **Result:** say which context is active and that a **new chat** must be opened for it to take effect. On error,
   show the command's message; do not try to work around it.
