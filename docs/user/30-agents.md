---
section: Using Harness Maxxing
---
# Agents: Claude Code, Codex CLI and Cursor CLI

Every session is run by an **agent CLI** installed on your server. Claude Code is the default; you can also use the
**Codex CLI** (OpenAI) and the **Cursor CLI** (`cursor-agent`). They share the same sessions, files, queue, stop button,
Telegram thread and history: only the agent that answers changes.

## Set it up

1. Install the CLI on the server and sign in once, as root:
   - Codex: `npm i -g @openai/codex`, then `codex login` (ChatGPT account) or give an API key.
   - Cursor: `curl https://cursor.com/install -fsS -o /tmp/cursor-install.sh`, then `bash /tmp/cursor-install.sh`, then `cursor-agent login`.
2. Settings → Agents → **Other agents: Codex and Cursor** shows each CLI's state (installed, signed in), the command to
   run on the server, an optional API key field and a test button.
3. Settings → Agents → **Default agent** shows which CLIs are installed and signed in. Pick the one new sessions use.
4. In a session, the **Agent** picker next to the model changes the agent for the next messages. Switching starts a
   new thread in the new CLI: the conversation shown above is kept, but the new agent does not remember it.

An API key works too: paste it in the agent's card (Settings → Agents → Other agents).

## Usage in the sidebar

Under the Claude bars, **Codex** shows its own plan windows (5 hours and week, read from Codex's files: no extra
call). **Cursor** reports no quota, so the sidebar shows the tokens Harness measured over 7 days for it (and for Codex
until it has run once). Hover for today's tokens and the reset time.

## What works the same

Streaming answers, tool cards (commands, file edits), stop, queue and steering, plan mode (read-only), permission modes
(bypass / accept edits / default), a model per session (type its name; empty = the CLI's default), Telegram.

## What is Claude-only

Claude Code skills and `CLAUDE.md`/memory loading by the CLI itself, Harness MCP servers loaded on demand, the
automatic cost in dollars (Codex and Cursor report tokens, not a price), the context gauge, compaction by Claude Code,
sub-agent display, short automatic titles made by Claude, and the Claude usage widget. Codex and Cursor read an
`AGENTS.md` in the topic folder instead of `CLAUDE.md`.

## Sub-agents: delegate from the shell

Any agent running in a session can hand work to another one with the `maxxing agent` command. Each sub-agent is a
normal session: it shows in the list (marked with an arrow, and with a branch icon when it has a worktree), you can open
it, read it, answer it or stop it like one you started yourself.

```bash
maxxing agent spawn "Fix the failing test in api/" --agent codex --worktree new:fix-api   # prints the id
maxxing agent list                 # the sub-agents of the current session
maxxing agent wait <id>            # wait until it is done, print its last answer
maxxing agent read <id> --tail 30  # the end of its conversation
maxxing agent send <id> "Also update the docs"
maxxing agent diff <id>            # what its worktree changed
maxxing agent merge <id> --delete  # merge its branch into the base branch, remove the worktree
```

`--wait` on `spawn` starts it and waits in one command. `--agent` is `claude`, `codex` or `cursor`. Ids can be
shortened to their first characters. A session can have 4 sub-agents working at once, and a sub-agent's own sub-agent
may not delegate again. `merge` stops when the worktree has uncommitted changes or when the merge conflicts (nothing
is left half-merged). Tell your agent the commands exist: for example add a line about them to the topic's `CLAUDE.md`
or `AGENTS.md`.
