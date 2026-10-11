"""The config block every evidence script writes beside its numbers.

Standing rule 2: every run saves its exact config (git SHA, versions, seeds, inputs
path, timestamp) next to its output. Standing rule 3, the evidence-location rule: a
missing or empty --inputs directory is an ERROR (exit 2) that names the path it
checked — never a finding of "unrecoverable" against a tree that never had the files.
"""
from __future__ import annotations

import datetime as _dt
import importlib
import platform
import re
import subprocess
import sys
from pathlib import Path

LAST_ERROR = ""

# Every git call and every default path is anchored here, never to the working
# directory: a git pathspec is cwd-relative, so run from paper/ a reconstruction
# silently matched nothing (QG Q1).
REPO = Path(__file__).resolve().parents[2]


def evidence(name: str) -> str:
    """The default location of an evidence file, independent of the working directory."""
    return str(REPO / "paper" / "evidence" / name)


def git_sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, cwd=REPO).strip()


# What a rebuild itself writes. `tree_clean` is a claim about the CODE that produced an
# evidence file, so the generated evidence is excluded: a full rebuild writes these in
# sequence, and the first producer's output would otherwise make every later one refuse.
GENERATED = "paper/evidence/"


def dirty_paths() -> list[str]:
    """Every path git reports as modified, staged or untracked, except generated evidence."""
    out = subprocess.check_output(["git", "status", "--porcelain"], text=True, cwd=REPO)
    paths = [ln[3:].strip() for ln in out.splitlines() if ln.strip()]
    return [p for p in paths if not p.startswith(GENERATED)]


# The tree state as it was BEFORE the run wrote anything, set by require_clean_tree().
# Sampling it inside block() instead would read dirty for an honest clean run, because
# scripts write their own evidence (and record copies) into the repository as they go.
_TREE_CLEAN: bool | None = None
_DIRTY: list[str] = []


def require_clean_tree(allow_dirty: bool = False) -> bool:
    """A7-2: a recorded `git_sha` identifies the code that produced the evidence ONLY if
    the tree was clean when it ran. It was not, once: science.json recorded a commit whose
    tree did not yet contain the fields the file carries, because the script was still
    uncommitted — the file looked pinned to code that could not have written it.

    So a dirty tree is refused (exit 2, naming what is dirty). `allow_dirty` does not
    suppress the fact: it records `tree_clean: false` and the paths in the block, which
    keeps a run that was not pinned from reading as one that was.
    """
    global _TREE_CLEAN, _DIRTY
    paths = dirty_paths()
    _TREE_CLEAN, _DIRTY = not paths, paths
    if not paths:
        return True
    shown = ", ".join(paths[:10]) + (f" (+{len(paths) - 10} more)" if len(paths) > 10 else "")
    if allow_dirty:
        print(f"WARNING: the working tree is dirty; this evidence is NOT pinned to its "
              f"recorded commit. Recorded as tree_clean false: {shown}", file=sys.stderr)
        return False
    print(f"ERROR: the working tree is dirty, so the recorded git_sha would not identify "
          f"the code that produced this evidence: {shown}", file=sys.stderr)
    raise SystemExit(2)


def versions(*modules: str) -> dict:
    out = {}
    for m in modules:
        try:
            out[m] = getattr(importlib.import_module(m), "__version__", "unknown")
        except Exception as e:  # noqa: BLE001 — recorded, not hidden
            out[m] = f"not importable: {type(e).__name__}"
    return out


HOME = Path.home().resolve()
# The checkout's enclosing project: both layouts this repository is checked out in
# (<parent>/projects/<repo> and <parent>/worktrees/<repo>-…) put it two levels up.
PARENT = REPO.parents[1]
_PLUGIN_CACHE = re.compile(r"~/\.claude/plugins/cache/[^/]+/(?P<name>[^/]+)/(?P<ver>[^/]+)")
_OTHER_HOME = re.compile(r"~/(?:[^/\s]+/)+(?P<base>[^/\s]+)")


def redact(value):
    """Absolute paths made publishable, recursively over every string an evidence file
    carries; numbers, digests and labels are untouched. The repository is public and its
    evidence recorded the machine's username and directory layout (QG F06).

    Coordinator's rule (#576): a path is either a LOCATOR inside the artifact — normalised
    to `<repo>/…` — or a claim about the ENVIRONMENT, which names the thing and its
    version, never the filesystem. So the enclosing project becomes `<parent-project>/…`,
    a plugin-cache path becomes `<plugin:NAME VERSION>/…`, and any other home-relative
    path keeps only its last component, `~/…/NAME`."""
    if isinstance(value, str):
        repo, home, parent = str(REPO), str(HOME), str(PARENT)
        s = value
        for prefix, token in ((repo, "<repo>"), (parent, "<parent-project>"), (home, "~")):
            if s == prefix or s.startswith(prefix + "/"):
                s = token + s[len(prefix):]
                break
        s = s.replace(repo + "/", "<repo>/").replace(parent + "/", "<parent-project>/").replace(home + "/", "~/")
        if parent.startswith(home + "/"):          # the same project, already written home-relative
            s = s.replace("~" + parent[len(home):], "<parent-project>")
        s = _PLUGIN_CACHE.sub(lambda m: f"<plugin:{m['name']} {m['ver']}>", s)
        return _OTHER_HOME.sub(lambda m: f"~/…/{m['base']}", s)
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def block(inputs_path: str | Path | None, extra: dict | None = None,
          modules: tuple[str, ...] = ()) -> dict:
    clean = _TREE_CLEAN if _TREE_CLEAN is not None else not dirty_paths()
    b = {
        "git_sha": git_sha(),
        # Whether that sha identifies the code that ran (A7-2); false carries the paths.
        "tree_clean": clean,
        "recorded_at": _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)
                        .isoformat().replace("+00:00", "Z"),
        "inputs_path": str(inputs_path) if inputs_path is not None else None,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "versions": versions(*modules),
    }
    if not clean:
        b["dirty_paths"] = list(_DIRTY) if _DIRTY else dirty_paths()
    b.update(extra or {})
    return redact(b)


def require_inputs(path: str | Path) -> Path:
    """Evidence-location rule. Exit 2 with the path NAMED on missing/empty."""
    global LAST_ERROR
    p = Path(path)
    if not p.is_dir():
        LAST_ERROR = f"inputs directory does not exist: {p}"
    elif not any(p.iterdir()):
        LAST_ERROR = f"inputs directory is empty: {p}"
    else:
        return p
    print(f"ERROR: {LAST_ERROR}", file=sys.stderr)
    raise SystemExit(2)
