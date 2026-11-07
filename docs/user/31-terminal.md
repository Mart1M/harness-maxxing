---
section: Workspace
---

# Terminal

The **Terminal** item in the sidebar runs Bash commands on your Harness server. Commands start in the configured workspace, so you can inspect files, run a project command or use installed command-line tools without opening SSH.

Type directly after the `$` prompt and press Enter. The command's output, errors and exit status appear above the prompt.

> Commands have the same permissions as Harness on this server. Read a command carefully before running it. Each entry is a separate command: use `cd folder && command` when a command must run in another folder.

Each command is stopped after two minutes. Very large output is shortened so the page stays responsive.
