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
   - Cursor: `curl https://cursor.com/install -fsS | bash`, then `cursor-agent login`.
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
