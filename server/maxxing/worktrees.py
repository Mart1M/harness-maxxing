"""Git worktrees of a topic: list them, create one, and check that a path is one of them.

A topic's repository is the topic folder itself when it is a git repository, else the repositories found inside it
(`gitview._walk`, a clone's linked worktrees counted once). The worktrees of a topic are those of these repositories
whose folder is inside the topic folder. A new one is made in `<repo>/.worktrees/<branch>` (that folder is added to the
repository's `info/exclude`, so it never shows as untracked), on a new branch or on an existing one.

Paths in and out are relative to the workspace, like a session's `path`. Git runs through `gitview._git`: no hooks, no
credential prompt. NOT thread-safe against a concurrent `git worktree add` on the same repository (git locks it).
"""
from __future__ import annotations

import re
from pathlib import Path

from . import gitview, workspace
from .gitview import GitError

WORKTREE_DIR = ".worktrees"
ADD_TIMEOUT = 180                    # checking out a big repository takes longer than a read
_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,99}\Z")


class WorktreeError(Exception):
    """Error carrying an HTTP status and an API code."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _rel(p: Path) -> str:
    return str(p.resolve().relative_to(workspace.root().resolve()))


def _topic(path: str) -> Path:
    try:
        return workspace.topic_dir(path).resolve()
    except ValueError as e:
        raise WorktreeError(400, "bad_path", str(e)) from None


def repos(path: str) -> list[Path]:
    """The repositories (main working trees) of a topic, sorted; [] when it holds none."""
    topic = _topic(path)
    if (topic / ".git").exists():
        found = [topic]
    else:
        found = gitview._walk(topic)
    out: dict[Path, None] = {}
    for d in found:
        main = gitview._main_clone(d) or d
        out[main.resolve()] = None
    return sorted(out)


def _parse(text: str) -> list[dict]:
    """`git worktree list --porcelain` -> [{path, head, branch|None}], bare and prunable entries left out."""
    out, cur = [], {}
    for line in text.splitlines() + [""]:
        if not line:
            if cur.get("path") and not cur.get("bare") and not cur.get("prunable"):
                out.append({"path": cur["path"], "head": cur.get("head", ""), "branch": cur.get("branch")})
            cur = {}
            continue
        key, _, val = line.partition(" ")
        if key == "worktree":
            cur["path"] = val
        elif key == "HEAD":
            cur["head"] = val[:12]
        elif key == "branch":
            cur["branch"] = val.removeprefix("refs/heads/")
        elif key in ("bare", "prunable"):
            cur[key] = True
    return out


def listing(path: str) -> list[dict]:
    """Every worktree of the topic: `{repo, repo_name, path, name, branch, head, main}`. `branch` is None for a
    detached HEAD; `main` marks the repository's own working tree."""
    topic = _topic(path)
    out = []
    for repo in repos(path):
        try:
            entries = _parse(gitview._git(repo, "worktree", "list", "--porcelain"))
        except GitError:
            continue                                          # unreadable repository: not offered
        for e in entries:
            p = Path(e["path"])
            try:
                p = p.resolve()
                p.relative_to(topic)
            except (OSError, ValueError):
                continue                                       # outside this topic: not its worktree
            if not p.is_dir():
                continue
            out.append({"repo": _rel(repo), "repo_name": repo.name, "path": _rel(p),
                        "name": p.name if p != repo else repo.name,
                        "branch": e["branch"], "head": e["head"], "main": p == repo})
    return out


def check_ref(name: str, what: str = "branch") -> str:
    name = (name or "").strip()
    if not _REF_RE.match(name) or ".." in name or "//" in name or name.endswith((".lock", "/", ".")):
        raise WorktreeError(400, f"bad_{what}", f"Not a valid {what} name: {name!r}")
    return name


def resolve(path: str, worktree: str) -> str:
    """`worktree` (relative to the workspace) when it is one of the topic's worktrees, else 400 `bad_worktree`."""
    wanted = (worktree or "").strip().strip("/")
    for w in listing(path):
        if w["path"] == wanted:
            return wanted
    raise WorktreeError(400, "bad_worktree", f"Not a worktree of this topic: {worktree!r}")


def _exclude(repo: Path) -> None:
    """Ignore `.worktrees/` in the repository without touching its tracked .gitignore (best effort)."""
    try:
        common = gitview._git(repo, "rev-parse", "--git-common-dir").strip()
        d = Path(common) if Path(common).is_absolute() else repo / common
        f = d / "info" / "exclude"
        have = f.read_text() if f.is_file() else ""
        if f"{WORKTREE_DIR}/" not in have.split():
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(have + ("" if not have or have.endswith("\n") else "\n") + f"{WORKTREE_DIR}/\n")
    except (GitError, OSError):
        pass


def create(path: str, branch: str, repo: str = "", base: str = "") -> dict:
    """Make `<repo>/.worktrees/<branch>` for the topic and return its `listing` entry. The branch is created from
    `base` (default: the repository's HEAD) unless it exists already. 404 `no_repo` when the topic holds no
    repository, 409 `exists` when the folder is taken or the branch is checked out elsewhere."""
    branch = check_ref(branch)
    base = check_ref(base, "base") if (base or "").strip() else ""
    found = repos(path)
    if not found:
        raise WorktreeError(404, "no_repo", "This topic holds no git repository")
    wanted = (repo or "").strip().strip("/")
    main = next((r for r in found if _rel(r) == wanted), None) if wanted else found[0]
    if main is None:
        raise WorktreeError(400, "bad_repo", f"Not a repository of this topic: {repo!r}")
    dest = main / WORKTREE_DIR / branch.replace("/", "-")
    if dest.exists():
        raise WorktreeError(409, "exists", f"{_rel(dest)} already exists")
    try:
        gitview._git(main, "check-ref-format", "--branch", branch)
        known = True
        try:
            gitview._git(main, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}")
        except GitError:
            known = False
        dest.parent.mkdir(parents=True, exist_ok=True)
        if known:
            gitview._git(main, "worktree", "add", str(dest), branch, timeout=ADD_TIMEOUT)
        else:
            gitview._git(main, "worktree", "add", "-b", branch, str(dest), *([base] if base else []),
                         timeout=ADD_TIMEOUT)
    except GitError as e:
        code = "exists" if "already" in e.message else "git_failed"
        raise WorktreeError(409 if code == "exists" else 400, code, e.message) from None
    _exclude(main)
    gitview.clear_cache()
    rel = _rel(dest)
    return next(w for w in listing(path) if w["path"] == rel)
