"""Usage of the non-Claude agents, for the sidebar (`GET /api/usage/providers`).

* Codex: the CLI writes its plan limits (5-hour and weekly windows, % used, reset time) in every rollout file it keeps
  (`$CODEX_HOME/sessions/**/rollout-*.jsonl`, `token_count` events). The newest one is read: no call, no token.
* Cursor: the CLI exposes no quota. Only what Harness itself measured is shown: tokens used by Cursor turns.
* Both also get `tokens` (today / last 7 days) from the per-provider counters of the sessions (meta `provider_days`).
"""
from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path

from . import config
from .sessions import providers, store

SCAN_FILES = 6               # newest rollout files looked at for a rate_limits reading
TAIL_BYTES = 262_144         # read this much of the end of a rollout file (a token_count is near the end)
CACHE_S = 20.0
_cache: dict = {"at": 0.0, "value": None}


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or (Path(os.environ.get("HOME") or "~").expanduser() / ".codex"))


def _window(w: object, now: float) -> dict | None:
    if not isinstance(w, dict):
        return None
    pct = w.get("used_percent")
    if not isinstance(pct, (int, float)) or isinstance(pct, bool) or not math.isfinite(pct):
        return None
    reset = w.get("resets_at")
    reset = float(reset) if isinstance(reset, (int, float)) and not isinstance(reset, bool) and math.isfinite(reset) else None
    if reset is not None and reset <= now:                  # the window has rolled over since that reading
        return {"pct": 0.0, "resets_at": None}
    return {"pct": min(max(round(float(pct), 1), 0.0), 100.0), "resets_at": reset}


def codex_limits(now: float | None = None) -> dict | None:
    """Last rate limits Codex wrote: {five_hour, seven_day, plan, seen_at} or None (never run, no reading)."""
    now = time.time() if now is None else now
    root = codex_home() / "sessions"
    try:
        files = sorted(root.glob("**/rollout-*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:SCAN_FILES]
    except OSError:
        return None
    for f in files:
        try:
            size = f.stat().st_size
            with open(f, "rb") as fh:
                fh.seek(max(0, size - TAIL_BYTES))
                lines = fh.read().decode("utf-8", "replace").splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            if '"rate_limits"' not in line:
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            p = ev.get("payload") if isinstance(ev, dict) and isinstance(ev.get("payload"), dict) else ev
            rl = p.get("rate_limits") if isinstance(p, dict) else None
            if not isinstance(rl, dict):
                continue
            five, week = _window(rl.get("primary"), now), _window(rl.get("secondary"), now)
            if five is None and week is None:
                continue
            seen = ev.get("timestamp")
            return {"five_hour": five, "seven_day": week,
                    "plan": str(rl["plan_type"]).capitalize() if rl.get("plan_type") else None,
                    "seen_at": f.stat().st_mtime if not isinstance(seen, (int, float)) else seen}
    return None


def tokens_by_provider(now: float | None = None) -> dict[str, dict]:
    """{provider: {today, week}} from the sessions' `provider_days` counters (tokens of Harness turns)."""
    now = time.time() if now is None else now
    today = time.strftime("%Y-%m-%d", time.localtime(now))
    week = {time.strftime("%Y-%m-%d", time.localtime(now - i * 86400)) for i in range(7)}
    out = {p: {"today": 0, "week": 0} for p in providers.PROVIDERS}
    for sid in store.list_ids():
        m = store.read_cached(sid)
        pd = m.get("provider_days") if isinstance(m, dict) else None
        if not isinstance(pd, dict):
            continue
        for prov, days in pd.items():
            if prov not in out or not isinstance(days, dict):
                continue
            for day, n in days.items():
                if isinstance(n, int) and not isinstance(n, bool):
                    if day in week:
                        out[prov]["week"] += n
                    if day == today:
                        out[prov]["today"] += n
    return out


def usage(force: bool = False) -> dict:
    """{codex: {...}, cursor: {...}}: `available` = real plan limits (bars); `tokens` = measured by Harness."""
    now = time.time()
    if not force and _cache["value"] is not None and now - _cache["at"] < CACHE_S:
        return _cache["value"]
    toks = tokens_by_provider(now)
    out: dict = {}
    for name in (providers.CODEX, providers.CURSOR):
        item: dict = {"id": name, "label": providers.label(name), "available": False, "five_hour": None,
                      "seven_day": None, "plan": None, "tokens": toks[name]}
        if name == providers.CODEX:
            lim = codex_limits(now)
            if lim:
                item.update(lim, available=True, source="codex")
        out[name] = item
    _cache.update(at=now, value=out)
    return out
