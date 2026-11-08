"""Git worktrees of a topic (the new-session picker). See docs/dev/API.md#worktrees."""
from __future__ import annotations

import asyncio
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException

from .. import worktrees
from ..worktrees import WorktreeError
from ..security import require_auth

router = APIRouter(prefix="/api/worktrees", tags=["worktrees"], dependencies=[Depends(require_auth)])


async def _call(fn: Callable[..., Any], *a: Any, **kw: Any) -> Any:
    try:
        return await asyncio.to_thread(fn, *a, **kw)
    except WorktreeError as e:
        raise HTTPException(e.status, detail={"error": e.code, "message": e.message}) from None


@router.get("")
async def list_worktrees(path: str = ""):
    return await _call(worktrees.listing, path)
