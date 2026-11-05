#!/usr/bin/env python3
"""Fake `codex` CLI for tests: `codex exec [opts] [resume ID] -` with JSONL events modelled on codex-cli 0.160.
Threads are remembered in $FAKE_CODEX_DIR; resuming an unknown id fails. Calls are appended to calls.jsonl.
Prompt keywords: FAIL (turn.failed)."""
import json
import os
import sys
import uuid
from pathlib import Path

STORE = Path(os.environ.get("FAKE_CODEX_DIR") or "/tmp/fake-codex")
STORE.mkdir(parents=True, exist_ok=True)
argv = sys.argv[1:]
if argv[:1] == ["login"]:
    print("Logged in using ChatGPT")
    sys.exit(0)
if argv[:1] != ["exec"]:
    sys.exit(2)
prompt = sys.stdin.read()
resume = argv[argv.index("resume") + 1] if "resume" in argv else None
with open(STORE / "calls.jsonl", "a") as f:
    f.write(json.dumps({"argv": argv, "prompt": prompt, "cwd": os.getcwd()}) + "\n")


def out(ev: dict) -> None:
    print(json.dumps(ev), flush=True)


if resume:
    if not (STORE / resume).exists():
        print(f"Error: no saved session found with ID {resume}", file=sys.stderr)
        sys.exit(1)
    tid = resume
else:
    tid = str(uuid.uuid4())
    (STORE / tid).write_text("1")
out({"type": "thread.started", "thread_id": tid})
out({"type": "turn.started"})
if "FAIL" in prompt:
    out({"type": "error", "message": "boom"})
    out({"type": "turn.failed", "error": {"message": "boom"}})
    sys.exit(1)
out({"type": "item.started", "item": {"id": "item_0", "type": "command_execution", "command": "echo hi",
                                      "aggregated_output": "", "exit_code": None, "status": "in_progress"}})
out({"type": "item.completed", "item": {"id": "item_0", "type": "command_execution", "command": "echo hi",
                                        "aggregated_output": "hi\n", "exit_code": 0, "status": "completed"}})
out({"type": "item.completed", "item": {"id": "item_1", "type": "agent_message", "text": "codex says ok"}})
out({"type": "turn.completed", "usage": {"input_tokens": 100, "cached_input_tokens": 40,
                                         "cache_write_input_tokens": 0, "output_tokens": 5,
                                         "reasoning_output_tokens": 0}})
