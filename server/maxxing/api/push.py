"""iPhone push notifications: devices, Apple key, what is sent. See docs/dev/API.md#push."""
from __future__ import annotations

import asyncio
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import push
from ..push import PushError
from ..security import require_auth

router = APIRouter(prefix="/api/push", tags=["push"], dependencies=[Depends(require_auth)])


async def _call(fn: Callable[..., Any], *a: Any, **kw: Any) -> Any:
    try:
        return await asyncio.to_thread(fn, *a, **kw)
    except PushError as e:
        raise HTTPException(e.status, detail={"error": e.code, "message": e.message}) from None


class DeviceIn(BaseModel):
    token: str
    name: str = ""
    env: str = "production"


class SettingsIn(BaseModel):
    enabled: bool | None = None
    turns: str | None = None
    errors: bool | None = None
    crons: bool | None = None


class CredentialsIn(BaseModel):
    key: str | None = None
    key_id: str | None = None
    team_id: str | None = None
    topic: str | None = None


def _state() -> dict:
    return {"settings": push.settings(), "credentials": push.credentials_public(), "devices": push.list_devices()}


@router.get("")
async def state() -> dict:
    return await asyncio.to_thread(_state)


@router.put("/settings")
async def put_settings(body: SettingsIn) -> dict:
    await _call(push.save_settings, **body.model_dump())
    return await asyncio.to_thread(_state)


@router.put("/credentials")
async def put_credentials(body: CredentialsIn) -> dict:
    await _call(push.save_credentials, **body.model_dump())
    return await asyncio.to_thread(_state)


@router.delete("/credentials")
async def delete_credentials() -> dict:
    await asyncio.to_thread(push.clear_credentials)
    return await asyncio.to_thread(_state)


@router.post("/devices")
async def add_device(body: DeviceIn) -> dict:
    return await _call(push.register, body.token, body.name, body.env)


@router.delete("/devices/{device_id}")
async def remove_device(device_id: str) -> dict:
    if not await asyncio.to_thread(push.unregister, device_id):
        raise HTTPException(404, detail={"error": "not_found", "message": "Unknown device"})
    return await asyncio.to_thread(_state)


@router.post("/test")
async def test() -> dict:
    res = await _call(push.test)
    return {**res, **await asyncio.to_thread(_state)}


async def startup() -> None:
    push.install_hooks()
