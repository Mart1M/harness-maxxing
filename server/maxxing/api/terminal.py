"""Authenticated Bash console, rooted in the configured workspace."""
from __future__ import annotations

import asyncio
import contextlib
import os
import pty
import select
import signal
import subprocess
import time

from fastapi import APIRouter, Depends, HTTPException, WebSocket
from pydantic import BaseModel, Field
from starlette.websockets import WebSocketDisconnect

from .. import security, workspace
from ..security import require_auth

router = APIRouter(prefix="/api/terminal", tags=["terminal"])

TIMEOUT_S = 120
OUTPUT_LIMIT = 128 * 1024


class CommandIn(BaseModel):
    command: str = Field(min_length=1, max_length=20_000)


class _Pty:
    """A short-lived interactive Bash process. Its master fd is only read by the websocket task."""

    def __init__(self, cwd):
        master, slave = pty.openpty()
        try:
            self.proc = subprocess.Popen(["bash", "-i"], cwd=cwd, stdin=slave, stdout=slave, stderr=slave,
                                         close_fds=True, start_new_session=True)
        except BaseException:
            os.close(master)
            raise
        finally:
            os.close(slave)
        self.fd = master
        self.closed = False

    def read(self) -> bytes | None:
        if self.closed:
            return b""
        try:
            readable, _, _ = select.select([self.fd], [], [], 0.2)
            if not readable:
                return None
            return os.read(self.fd, 8192)
        except OSError:
            return b""

    def write(self, text: str) -> None:
        if not self.closed:
            os.write(self.fd, text.encode("utf-8", "replace"))

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            if self.proc.poll() is None:
                os.killpg(self.proc.pid, signal.SIGTERM)
                try:
                    self.proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    os.killpg(self.proc.pid, signal.SIGKILL)
                    self.proc.wait(timeout=2)
        except OSError:
            pass
        finally:
            with contextlib.suppress(OSError):
                os.close(self.fd)


@router.websocket("/ws")
async def shell(ws: WebSocket):
    """A same-origin authenticated interactive Bash terminal. Closing the tab ends its shell."""
    if not security.cookie_valid(ws.cookies.get(security.COOKIE)):
        await ws.close(code=4401)
        return
    cwd = workspace.root()
    if not cwd.is_dir():
        await ws.close(code=4409)
        return
    try:
        term = await asyncio.to_thread(_Pty, cwd)
    except OSError:
        await ws.close(code=1011)
        return
    await ws.accept()

    async def output() -> None:
        while True:
            data = await asyncio.to_thread(term.read)
            if data is None:
                continue
            if data:
                await ws.send_json({"t": "out", "data": data.decode("utf-8", "replace")})
            else:
                return

    reader = asyncio.create_task(output())
    try:
        while True:
            message = await ws.receive_json()
            data = message.get("data") if isinstance(message, dict) else None
            if not isinstance(data, str) or len(data) > 20_000:
                await ws.close(code=1008)
                return
            await asyncio.to_thread(term.write, data)
    except WebSocketDisconnect:
        pass
    finally:
        await asyncio.to_thread(term.close)
        reader.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await reader


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


@router.post("/run", dependencies=[Depends(require_auth)])
async def run(body: CommandIn):
    if not body.command.strip():
        raise HTTPException(422, detail={"error": "invalid_command", "message": "Enter a command"})
    # Bash may run for up to TIMEOUT_S. Keep the ASGI event loop free so the rest of the app stays responsive.
    return await asyncio.to_thread(_run, body.command)
