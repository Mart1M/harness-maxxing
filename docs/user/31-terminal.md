---
section: Workspace
---

# Terminal

The **Terminal** item in the sidebar runs Bash commands on your Harness server. Commands start in the configured workspace, so you can inspect files, run a project command or use installed command-line tools without opening SSH.

Type directly after the `$` prompt and press Enter. This is an interactive Bash session: programs such as `agent login` can ask a question and you can answer at the next prompt. Leaving the Terminal page closes the session.

> Commands have the same permissions as Harness on this server. Read a command carefully before running it. Each entry is a separate command: use `cd folder && command` when a command must run in another folder.

Each command is stopped after two minutes. Very large output is shortened so the page stays responsive.
