"""Processes page: commands running in repositories, their logs and an optional password-protected URL.
See docs/dev/API.md#processes."""
from __future__ import annotations

import asyncio
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .. import processes
from ..processes import ProcessError
from ..security import require_auth

router = APIRouter(prefix="/api/processes", tags=["processes"], dependencies=[Depends(require_auth)])


async def _call(fn: Callable[..., Any], *a: Any, **kw: Any) -> Any:
    try:
        return await asyncio.to_thread(fn, *a, **kw)
    except ProcessError as e:
        raise HTTPException(e.status, detail={"error": e.code, "message": e.message}) from None


class CreateIn(BaseModel):
    name: str = Field(max_length=40)
    repo: str = Field(max_length=500)
    command: str = Field(max_length=2000)
    port: int | None = Field(None, ge=1, le=65535)
    start: bool = True


class PublishIn(BaseModel):
    host: str | None = Field(None, max_length=253)     # own host name (DNS must point here); empty = a path of Harness' address


@router.get("")
async def list_processes():
    return await _call(processes.list_processes)


@router.post("")
async def create(body: CreateIn):
    return await _call(processes.create, body.name, body.repo, body.command, body.port, body.start)


@router.get("/{name}")
async def one(name: str):
    return await _call(processes.get_public, name)


@router.post("/{name}/start")
async def start(name: str):
    return await _call(processes.start, name)


@router.post("/{name}/stop")
async def stop(name: str):
    return await _call(processes.stop, name)


@router.post("/{name}/restart")
async def restart(name: str):
    return await _call(processes.restart, name)


@router.delete("/{name}")
async def delete(name: str):
    return await _call(processes.delete, name)


@router.get("/{name}/logs")
async def logs(name: str, lines: int = Query(200, ge=1, le=2000)):
    return await _call(processes.logs, name, lines)


@router.post("/{name}/publish")
async def publish(name: str, body: PublishIn | None = None):
    return await _call(processes.publish, name, body.host if body else None)


@router.delete("/{name}/publish")
async def unpublish(name: str):
    return await _call(processes.unpublish, name)


@router.get("/{name}/credentials")
async def credentials(name: str):
    return await _call(processes.credentials, name)
