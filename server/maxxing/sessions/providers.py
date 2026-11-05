"""Agent providers: which CLI runs a turn (Claude Code, Codex CLI, Cursor CLI).  STDLIB ONLY.

The rest of Harness (log, normaliser, UI, Telegram) speaks one vocabulary: Claude Code's stream-json. A provider
therefore has two jobs:

  * `build_args()`  - the argv of one turn (new thread or resume, model, permission mode);
  * `Adapter`       - turns the CLI's own stdout lines into Claude-shaped events (`system/init`, `assistant`,
                      `user` tool results, `result`), so `normalize.py` and the stats work unchanged.

Claude is the reference: its lines pass through untouched. Codex (`codex exec --json`) and Cursor
(`cursor-agent -p --output-format stream-json`) are translated. Both assign their thread id themselves: it is read
from the stream (`Adapter.thread_id`) and stored as the session's `csid`.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from typing import Any

CLAUDE, CODEX, CURSOR = "claude", "codex", "cursor"
PROVIDERS = (CLAUDE, CODEX, CURSOR)
LABELS = {CLAUDE: "Claude Code", CODEX: "Codex CLI", CURSOR: "Cursor CLI"}
BIN_ENV = {CLAUDE: "MAXXING_CLAUDE_BIN", CODEX: "MAXXING_CODEX_BIN", CURSOR: "MAXXING_CURSOR_BIN"}
BIN_NAMES = {CLAUDE: ("claude",), CODEX: ("codex",), CURSOR: ("cursor-agent", "agent")}
# Secrets (Keys in Settings, flagged "expose", or secrets.json) the CLIs read from their environment
AUTH_ENV = {CODEX: ("OPENAI_API_KEY", "CODEX_API_KEY"), CURSOR: ("CURSOR_API_KEY",)}
SECRET_FOR = {CODEX: "openai_api_key", CURSOR: "cursor_api_key"}        # secrets.json names (Settings -> Agents)
INSTALL = {CODEX: "npm i -g @openai/codex", CURSOR: "curl https://cursor.com/install -fsS | bash"}
LOGIN = {CODEX: "codex login", CURSOR: "cursor-agent login"}
KEY_HINT = {CODEX: "sk-…", CURSOR: "key_…"}
RESUME_LOST = re.compile(r"no conversation found|no (?:saved )?(?:session|chat|rollout|thread)s? .{0,80}found|"
                         r"session .{0,80}not found|chat .{0,80}not found|no such (?:session|chat)|"
                         r"invalid (?:session|chat)|could not resume|failed to resume", re.I)


def normalize_provider(value: object) -> str:
    v = str(value or "").strip().lower()
    return v if v in PROVIDERS else CLAUDE


def label(provider: str) -> str:
    return LABELS.get(provider, provider)


def binary(provider: str, path: str | None = None) -> str:
    """The provider's executable: $MAXXING_<P>_BIN, else the first name found on `path` (default: PATH)."""
    explicit = os.environ.get(BIN_ENV.get(provider, ""))
    if explicit:
        return explicit
    for name in BIN_NAMES.get(provider, (provider,)):
        found = shutil.which(name, path=path)
        if found:
            return found
    return BIN_NAMES.get(provider, (provider,))[0]


# ---- argv ---------------------------------------------------------------------------------------
def build_args(provider: str, exe: str, *, mode: str, model: str, csid: str, fresh: bool,
               cwd: str) -> list[str]:
    """argv for Codex or Cursor (Claude's is built by the runner: it carries many Claude-only flags).
    `mode` is Harness' permission mode: bypass | acceptEdits | default | plan. The prompt goes through stdin."""
    if provider == CODEX:
        args = [exe, "exec", "--json", "--skip-git-repo-check", "-C", cwd]
        if mode == "plan":
            args += ["-s", "read-only"]
        elif mode == "bypass":
            args += ["--dangerously-bypass-approvals-and-sandbox"]
        else:                                                # acceptEdits / default: edit the folder, no network
            args += ["-s", "workspace-write"]
        if model:
            args += ["-m", model]
        if not fresh and csid:                               # options first: `resume` takes only a few of them
            args += ["resume", csid]
        return args + ["-"]
    if provider == CURSOR:
        args = [exe, "-p", "--output-format", "stream-json", "--trust", "--workspace", cwd]
        if mode == "plan":
            args += ["--mode", "plan"]
        elif mode == "bypass":
            args += ["--force"]
        elif mode == "default":
            args += ["--auto-review"]
        else:
            args += ["--force", "--sandbox", "enabled"]
        if model:
            args += ["--model", model]
        if not fresh and csid:
            args += ["--resume", csid]
        return args
    raise ValueError(f"no argv builder for provider {provider!r}")


def resume_lost(provider: str, stderr: str, errors: list | None = None) -> bool:
    text = (stderr or "") + " " + " ".join(str(e) for e in errors or [])
    return bool(RESUME_LOST.search(text))


# ---- adapters -----------------------------------------------------------------------------------
def make_adapter(provider: str) -> "Adapter":
    return {CODEX: CodexAdapter, CURSOR: CursorAdapter}.get(provider, Adapter)()


class Adapter:
    """Pass-through (Claude). Subclasses translate one stdout line into zero or more Claude-shaped events."""
    thread_id: str | None = None

    def feed(self, line: str) -> list[dict]:
        try:
            ev = json.loads(line)
        except ValueError:
            return []
        return [ev] if isinstance(ev, dict) else []


def _text_event(text: str) -> dict:
    return {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}


def _tool_use(tid: str, name: str, inp: dict) -> dict:
    return {"type": "assistant", "message": {"role": "assistant",
            "content": [{"type": "tool_use", "id": tid, "name": name, "input": inp}]}}


def _tool_result(tid: str, text: str, error: bool = False) -> dict:
    return {"type": "user", "message": {"role": "user",
            "content": [{"type": "tool_result", "tool_use_id": tid, "content": text, "is_error": error}]}}


def _result(text: str, usage: dict, error: str | None = None, session_id: str | None = None) -> dict:
    ev: dict[str, Any] = {"type": "result", "subtype": "error" if error else "success", "is_error": bool(error),
                          "result": error or text, "usage": usage}
    if error:
        ev["errors"] = [error]
    if session_id:
        ev["session_id"] = session_id
    return ev


class CodexAdapter(Adapter):
    """`codex exec --json`: thread.started, turn.started, item.started / item.completed, turn.completed | turn.failed.
    Item types: agent_message, reasoning, command_execution, file_change, mcp_tool_call, web_search, todo_list."""

    def __init__(self) -> None:
        self.text = ""
        self.open: set[str] = set()                          # tool_use ids already emitted
        self.error: str | None = None

    def feed(self, line: str) -> list[dict]:
        try:
            ev = json.loads(line)
        except ValueError:
            return []
        if not isinstance(ev, dict):
            return []
        t = ev.get("type")
        if t == "thread.started":
            self.thread_id = str(ev.get("thread_id") or "") or None
            return [{"type": "system", "subtype": "init", "session_id": self.thread_id, "model": ev.get("model"),
                     "tools": [], "mcp_servers": []}]
        if t in ("item.started", "item.updated", "item.completed") and isinstance(ev.get("item"), dict):
            return self._item(t, ev["item"])
        if t == "turn.completed":
            u = ev.get("usage") if isinstance(ev.get("usage"), dict) else {}
            usage = {"input_tokens": int(u.get("input_tokens") or 0),
                     "cache_read_input_tokens": int(u.get("cached_input_tokens") or 0),
                     "cache_creation_input_tokens": int(u.get("cache_write_input_tokens") or 0),
                     "output_tokens": int(u.get("output_tokens") or 0)}
            return [_result(self.text, usage, self.error, self.thread_id)]
        if t == "turn.failed":
            err = ev.get("error")
            msg = (err.get("message") if isinstance(err, dict) else err) or "Codex turn failed"
            return [_result("", {}, str(msg), self.thread_id)]
        if t == "error":
            self.error = str(ev.get("message") or "Codex error")      # reported by turn.failed right after
        return []

    def _item(self, kind: str, it: dict) -> list[dict]:
        typ, iid = it.get("type"), str(it.get("id") or "")
        if typ == "agent_message":
            if kind != "item.completed" or not str(it.get("text") or "").strip():
                return []
            self.text = str(it["text"])
            return [_text_event(self.text)]
        if typ == "reasoning":
            text = str(it.get("text") or "")
            if kind != "item.completed" or not text.strip():
                return []
            return [{"type": "assistant", "message": {"role": "assistant",
                     "content": [{"type": "thinking", "thinking": text}]}}]
        name, inp, out, bad = self._tool(typ, it)
        if name is None:
            return []
        evs: list[dict] = []
        if iid not in self.open:
            self.open.add(iid)
            evs.append(_tool_use(iid, name, inp))
        if kind == "item.completed":
            evs.append(_tool_result(iid, out, bad))
        return evs

    @staticmethod
    def _tool(typ: object, it: dict) -> tuple[str | None, dict, str, bool]:
        if typ == "command_execution":
            code = it.get("exit_code")
            return "Bash", {"command": str(it.get("command") or "")}, str(it.get("aggregated_output") or ""), \
                   (code not in (None, 0)) or it.get("status") == "failed"
        if typ == "file_change":
            changes = [c for c in it.get("changes") or [] if isinstance(c, dict)]
            first = str(changes[0].get("path") or "") if changes else ""
            summary = "\n".join(f"{c.get('kind', 'update')} {c.get('path', '')}" for c in changes)
            return "Edit", {"file_path": first, "changes": changes}, summary, it.get("status") == "failed"
        if typ == "mcp_tool_call":
            res = it.get("result")
            text = json.dumps(res, ensure_ascii=False)[:4000] if res is not None else str(it.get("error") or "")
            return f"mcp__{it.get('server') or 'server'}__{it.get('tool') or 'tool'}", \
                   it.get("arguments") if isinstance(it.get("arguments"), dict) else {}, text, \
                   it.get("status") == "failed"
        if typ == "web_search":
            return "WebSearch", {"query": str(it.get("query") or "")}, "", False
        return None, {}, "", False


# Cursor tool_call objects are keyed by tool kind (shellToolCall, readToolCall...): the Claude tool they look like
_CURSOR_TOOLS = {"shell": "Bash", "read": "Read", "write": "Write", "edit": "Edit", "delete": "Delete", "grep": "Grep",
                 "glob": "Glob", "ls": "LS", "todo": "TodoWrite", "web": "WebFetch", "websearch": "WebSearch",
                 "mcp": "mcp"}


class CursorAdapter(Adapter):
    """`cursor-agent -p --output-format stream-json`: already close to Claude's (system/init, assistant, result).
    Changes: the user echo and thinking deltas are dropped, `tool_call` started/completed become tool_use /
    tool_result, camelCase usage becomes Claude's keys."""

    def __init__(self) -> None:
        self.text = ""

    def feed(self, line: str) -> list[dict]:
        try:
            ev = json.loads(line)
        except ValueError:
            return []
        if not isinstance(ev, dict):
            return []
        t = ev.get("type")
        sid = ev.get("session_id")
        if sid and not self.thread_id:
            self.thread_id = str(sid)
        if t == "system" and ev.get("subtype") == "init":
            ev.setdefault("tools", [])
            ev.setdefault("mcp_servers", [])
            return [ev]
        if t == "assistant":
            for b in (ev.get("message") or {}).get("content") or []:
                if isinstance(b, dict) and b.get("type") == "text" and (b.get("text") or "").strip():
                    self.text = b["text"]
            return [ev]
        if t == "tool_call":
            return self._tool(ev)
        if t == "result":
            u = ev.get("usage") if isinstance(ev.get("usage"), dict) else {}
            ev["usage"] = {"input_tokens": int(u.get("inputTokens") or 0),
                           "cache_read_input_tokens": int(u.get("cacheReadTokens") or 0),
                           "cache_creation_input_tokens": int(u.get("cacheWriteTokens") or 0),
                           "output_tokens": int(u.get("outputTokens") or 0)}
            if ev.get("is_error") and not ev.get("errors"):
                ev["errors"] = [str(ev.get("result") or "Cursor turn failed")]
            return [ev]
        return []                                            # user echo, thinking deltas, anything unknown

    def _tool(self, ev: dict) -> list[dict]:
        call = ev.get("tool_call") if isinstance(ev.get("tool_call"), dict) else {}
        key = next(iter(call), "")
        body = call.get(key) if isinstance(call.get(key), dict) else {}
        kind = re.sub(r"ToolCall$", "", key)
        name = _CURSOR_TOOLS.get(kind.lower(), kind[:1].upper() + kind[1:] or "Tool")
        args = body.get("args") if isinstance(body.get("args"), dict) else {}
        if "command" in args:
            inp = {"command": args["command"]}
        elif "path" in args:
            inp = {**args, "file_path": args["path"]}
        else:
            inp = args
        tid = str(ev.get("call_id") or f"{key}-{ev.get('timestamp_ms', '')}")
        if ev.get("subtype") == "started":
            return [_tool_use(tid, name, inp)]
        if ev.get("subtype") == "completed":
            res = body.get("result") if isinstance(body.get("result"), dict) else {}
            ok = res.get("success")
            bad = "error" in res or "rejected" in res
            payload = res.get("error") if bad else ok
            text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)[:4000] if payload else ""
            if isinstance(ok, dict) and isinstance(ok.get("stdout"), str):
                text = ok["stdout"] + (("\n" + ok["stderr"]) if ok.get("stderr") else "")
            return [_tool_result(tid, text, bad)]
        return []
