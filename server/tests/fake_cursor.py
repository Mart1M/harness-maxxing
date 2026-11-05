#!/usr/bin/env python3
"""Fake `cursor-agent` for tests: `-p --output-format stream-json [--resume ID]`, prompt on stdin. Events modelled on
cursor-agent 2026.11. Threads in $FAKE_CURSOR_DIR; resuming an unknown chat fails. Prompt keyword: FAIL."""
import json
import os
import sys
import uuid
from pathlib import Path

STORE = Path(os.environ.get("FAKE_CURSOR_DIR") or "/tmp/fake-cursor")
STORE.mkdir(parents=True, exist_ok=True)
argv = sys.argv[1:]
if argv[:1] == ["status"]:
    print("✓ Logged in as test@example.com")
    sys.exit(0)
prompt = sys.stdin.read()
resume = argv[argv.index("--resume") + 1] if "--resume" in argv else None
with open(STORE / "calls.jsonl", "a") as f:
    f.write(json.dumps({"argv": argv, "prompt": prompt, "cwd": os.getcwd()}) + "\n")


def out(ev: dict) -> None:
    print(json.dumps(ev), flush=True)


if resume:
    if not (STORE / resume).exists():
        print(f"Chat {resume} not found", file=sys.stderr)
        sys.exit(1)
    sid = resume
else:
    sid = str(uuid.uuid4())
    (STORE / sid).write_text("1")
out({"type": "system", "subtype": "init", "session_id": sid, "model": "Auto", "permissionMode": "default"})
out({"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": prompt}]}, "session_id": sid})
out({"type": "thinking", "subtype": "delta", "text": "hmm", "session_id": sid})
if "FAIL" in prompt:
    out({"type": "result", "subtype": "error", "is_error": True, "result": "cursor failed", "session_id": sid})
    sys.exit(1)
out({"type": "tool_call", "subtype": "started", "call_id": "c1", "session_id": sid,
     "tool_call": {"shellToolCall": {"args": {"command": "echo hi"}}}})
out({"type": "tool_call", "subtype": "completed", "call_id": "c1", "session_id": sid,
     "tool_call": {"shellToolCall": {"args": {"command": "echo hi"},
                                     "result": {"success": {"stdout": "hi\n", "stderr": "", "exitCode": 0}}}}})
out({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "cursor says ok"}]},
     "session_id": sid})
out({"type": "result", "subtype": "success", "is_error": False, "result": "cursor says ok", "session_id": sid,
     "usage": {"inputTokens": 100, "outputTokens": 5, "cacheReadTokens": 40, "cacheWriteTokens": 0}})
