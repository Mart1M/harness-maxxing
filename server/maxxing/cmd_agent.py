"""`maxxing agent …`: delegate work to other sessions (sub-agents) from the shell.

Run from inside a session (its turn sets MAXXING_SESSION_ID) the new session is a child of it and shows in the web
list like one started by hand. Any agent that can run a shell command (Claude, Codex, Cursor) can use it.

  maxxing agent spawn "task" [--agent codex] [--worktree new:fix-x] [--wait]
  maxxing agent list | wait ID | read ID | send ID "text" | stop ID | diff ID | merge ID [--delete]
"""
from __future__ import annotations

import json
import os
import sys

from . import cli

AGENTS = ("claude", "codex", "cursor")


def _configure(p) -> None:
    sub = p.add_subparsers(dest="agent_cmd", required=True)
    s = sub.add_parser("spawn", help="start a sub-agent session; prints its id")
    s.add_argument("prompt", help="the task ('-' reads it from stdin)")
    s.add_argument("--agent", choices=AGENTS, help="CLI that runs it (default: the server's default agent)")
    s.add_argument("--model")
    s.add_argument("--title")
    s.add_argument("--path", help="topic path (default: the parent session's topic)")
    s.add_argument("--worktree", help="new:BRANCH[@BASE], or an existing worktree of the topic (path, folder or branch)")
    s.add_argument("--plan", action="store_true", help="read-only turns that end with a plan")
    s.add_argument("--wait", action="store_true", help="wait for it to finish and print its answer")
    s.add_argument("--timeout", type=float, help="seconds to wait (with --wait)")
    s.add_argument("--json", action="store_true")
    l = sub.add_parser("list", help="sub-agents of this session (or --all sessions with a parent)")
    l.add_argument("--all", action="store_true")
    l.add_argument("--json", action="store_true")
    w = sub.add_parser("wait", help="wait until the sub-agent has finished, print its last answer")
    w.add_argument("id")
    w.add_argument("--timeout", type=float, help="seconds; exit code 124 when it is not finished by then")
    w.add_argument("--json", action="store_true")
    r = sub.add_parser("read", help="print the end of its conversation")
    r.add_argument("id")
    r.add_argument("--tail", type=int, default=20)
    m = sub.add_parser("send", help="send it another message")
    m.add_argument("id")
    m.add_argument("text")
    st = sub.add_parser("stop", help="abort its turn and clear its queue")
    st.add_argument("id")
    d = sub.add_parser("diff", help="what its worktree changed")
    d.add_argument("id")
    mg = sub.add_parser("merge", help="merge its worktree branch into the base branch")
    mg.add_argument("id")
    mg.add_argument("--delete", action="store_true", help="then remove the worktree and its branch")


def _full_id(prefix: str) -> str:
    """An id or a unique start of one (what `list` prints)."""
    from .sessions import store
    hits = [i for i in store.list_ids() if i.startswith(prefix)]
    if len(hits) != 1:
        raise SystemExit(f"maxxing agent: {'no session' if not hits else 'several sessions'} starting with {prefix!r}")
    return hits[0]


def _line(s: dict) -> str:
    where = s.get("worktree", "").rsplit("/", 1)[-1] or "-"
    state = "running" if s["state"] == "running" or s["queue"] else s["state"]
    return f"{s['id'][:8]}  {state:8}  {s['provider']:7}  {where:20}  {s['title']}"


def _handler(a) -> int:
    from .sessions import agents, service
    from .sessions.service import SessionError
    me = os.environ.get("MAXXING_SESSION_ID") or None
    try:
        return _run(a, agents, service, me)
    except SessionError as e:
        print(f"maxxing agent: {e.message} ({e.code})", file=sys.stderr)
        return 1


def _finish(agents, sid: str, timeout: float | None, as_json: bool) -> int:
    try:
        s = agents.wait(sid, timeout)
    except TimeoutError:
        print(f"maxxing agent: {sid[:8]} is still working", file=sys.stderr)
        return 124
    text = agents.answer(sid)
    if as_json:
        print(json.dumps({"id": sid, "state": s["state"], "error": s["error"], "answer": text}))
    else:
        print(text or (f"[{s['state']}] {s['error']}" if s["error"] else "[no answer]"))
    return 1 if s["state"] == "error" else 0


def _run(a, agents, service, me) -> int:
    c = a.agent_cmd
    if c == "spawn":
        prompt = sys.stdin.read() if a.prompt == "-" else a.prompt
        s = agents.spawn(me, prompt, path=a.path, agent=a.agent, model=a.model, title=a.title, worktree=a.worktree, plan=a.plan)
        if a.wait:
            print(f"started {s['id'][:8]}", file=sys.stderr)
            return _finish(agents, s["id"], a.timeout, a.json)
        print(json.dumps(s) if a.json else s["id"])
        return 0
    if c == "list":
        rows = [s for s in service.list_sessions(None, None) if (s.get("parent") if a.all else s.get("parent") == me)]
        if a.all is False and not me:
            print("maxxing agent: not inside a session: use --all", file=sys.stderr)
            return 1
        print(json.dumps(rows) if a.json else "\n".join(_line(s) for s in rows) or "no sub-agents")
        return 0
    sid = _full_id(a.id)
    if c == "wait":
        return _finish(agents, sid, a.timeout, a.json)
    if c == "read":
        print("\n".join(agents.transcript(sid, a.tail)))
    elif c == "send":
        r = service.send_message(sid, a.text, source="web")
        print("queued" if r.get("queued") else "sent")
    elif c == "stop":
        service.stop(sid)
        print("stopped")
    elif c == "diff":
        print(agents.diff(sid))
    elif c == "merge":
        r = agents.merge(sid, a.delete)
        print(f"merged {r['merged']} into {r['into']}" + (" and removed the worktree" if r["deleted"] else ""))
    return 0


cli.register("agent", "delegate work to sub-agent sessions (spawn, wait, read, diff, merge)", _configure, _handler)
