"""Authenticated Bash console, rooted in the configured workspace."""
from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import workspace
from ..security import require_auth

router = APIRouter(prefix="/api/terminal", tags=["terminal"], dependencies=[Depends(require_auth)])

TIMEOUT_S = 120
OUTPUT_LIMIT = 128 * 1024


class CommandIn(BaseModel):
    command: str = Field(min_length=1, max_length=20_000)


def _run(command: str) -> dict:
    """Run one non-interactive Bash command in the workspace, with a bounded lifetime/output."""
    cwd = workspace.root()
    if not cwd.is_dir():
        raise HTTPException(409, detail={"error": "workspace_missing", "message": "The workspace folder does not exist"})
    started = time.monotonic()
    try:
        p = subprocess.Popen(
            ["bash", "-lc", command], cwd=cwd, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace",
            start_new_session=True,
        )
    except OSError as e:
        raise HTTPException(502, detail={"error": "spawn_failed", "message": str(e)}) from None
    timed_out = False
    try:
        stdout, stderr = p.communicate(timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        timed_out = True
        with contextlib.suppress(ProcessLookupError):
            os.killpg(p.pid, signal.SIGTERM)
        try:
            stdout, stderr = p.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(p.pid, signal.SIGKILL)
            stdout, stderr = p.communicate()
        stderr = (stderr or "") + f"\nCommand timed out after {TIMEOUT_S} seconds."
    truncated = len(stdout) > OUTPUT_LIMIT or len(stderr) > OUTPUT_LIMIT
    if len(stdout) > OUTPUT_LIMIT:
        stdout = "… output truncated …\n" + stdout[-OUTPUT_LIMIT:]
    if len(stderr) > OUTPUT_LIMIT:
        stderr = "… output truncated …\n" + stderr[-OUTPUT_LIMIT:]
    return {"stdout": stdout, "stderr": stderr, "code": 124 if timed_out else p.returncode,
            "timed_out": timed_out, "truncated": truncated, "cwd": str(cwd),
            "duration_s": round(time.monotonic() - started, 3)}


@router.post("/run")
async def run(body: CommandIn):
    if not body.command.strip():
        raise HTTPException(422, detail={"error": "invalid_command", "message": "Enter a command"})
    return _run(body.command)
