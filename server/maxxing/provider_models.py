"""Model lists of the non-Claude agents (the model picker of a Codex or Cursor session).

* Codex: `$CODEX_HOME/models_cache.json` (kept by the CLI) or `codex debug models` (JSON catalog); the entries it
  marks `visibility: hide` are internal.
* Cursor: `cursor-agent --list-models` -> lines `<id> - <label>`; `auto` is the CLI's own choice.
Results are kept a few minutes: the CLIs fetch the list from their servers.
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

from .provider_usage import codex_home
from .sessions import providers, spawn

CACHE_S = 300.0
_cache: dict[str, tuple[float, list[dict]]] = {}
_CURSOR_LINE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._:\[\],=/-]*)\s+-\s+(.+?)\s*$")


def _codex_from_catalog(d: object) -> list[dict]:
    models = d.get("models") if isinstance(d, dict) else None
    out = []
    for m in sorted([x for x in models or [] if isinstance(x, dict)], key=lambda x: x.get("priority") or 0):
        slug = m.get("slug")
        if not isinstance(slug, str) or not slug or m.get("visibility") == "hide":
            continue
        out.append({"id": slug, "label": str(m.get("display_name") or slug), "description": str(m.get("description") or ""),
                    "context_window": m.get("context_window") if isinstance(m.get("context_window"), int) else None})
    return out


def _codex_models(exe: str, env: dict) -> list[dict]:
    try:
        found = _codex_from_catalog(json.loads(Path(codex_home() / "models_cache.json").read_text()))
        if found:
            return found
    except (OSError, ValueError):
        pass
    r = subprocess.run([exe, "debug", "models"], capture_output=True, text=True, timeout=30, env=env)
    return _codex_from_catalog(json.loads(r.stdout)) if r.returncode == 0 and r.stdout.strip() else []


def _cursor_models(exe: str, env: dict) -> list[dict]:
    r = subprocess.run([exe, "--list-models"], capture_output=True, text=True, timeout=30, env=env)
    return _cursor_models_from(r.stdout)


def _cursor_models_from(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        m = _CURSOR_LINE.match(line.strip())
        if m:
            label = re.sub(r"\s*\((?:current|default)[^)]*\)\s*$", "", m.group(2)).strip()
            out.append({"id": m.group(1), "label": label or m.group(1), "description": "", "context_window": None})
    return out


def models(provider: str, force: bool = False) -> list[dict]:
    """[{id, label, description, context_window}] for codex / cursor; [] when the CLI is missing or fails."""
    now = time.time()
    hit = _cache.get(provider)
    if hit and not force and now - hit[0] < CACHE_S:
        return hit[1]
    env = {**spawn.base_env(), **spawn.provider_env(provider)}
    exe = providers.binary(provider, env["PATH"])
    try:
        out = _codex_models(exe, env) if provider == providers.CODEX else _cursor_models(exe, env)
    except (OSError, ValueError, subprocess.SubprocessError):
        out = []
    if out:
        _cache[provider] = (now, out)
    return out
