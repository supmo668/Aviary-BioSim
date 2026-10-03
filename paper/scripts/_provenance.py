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


def versions(*modules: str) -> dict:
    out = {}
    for m in modules:
        try:
            out[m] = getattr(importlib.import_module(m), "__version__", "unknown")
        except Exception as e:  # noqa: BLE001 — recorded, not hidden
            out[m] = f"not importable: {type(e).__name__}"
    return out


HOME = Path.home().resolve()


def redact(value):
    """Absolute paths made publishable: a path inside this repository becomes `<repo>/…`,
    one under the home directory becomes `~/…`. Applied to every string an evidence file
    carries, recursively; numbers, digests and labels are untouched. The repository is
    public and its evidence recorded the machine's username and directory layout (QG F06)."""
    if isinstance(value, str):
        repo, home = str(REPO), str(HOME)
        if value.startswith(repo + "/") or value == repo:
            return "<repo>" + value[len(repo):]
        if value.startswith(home + "/") or value == home:
            return "~" + value[len(home):]
        return value.replace(repo + "/", "<repo>/").replace(home + "/", "~/")
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def block(inputs_path: str | Path | None, extra: dict | None = None,
          modules: tuple[str, ...] = ()) -> dict:
    b = {
        "git_sha": git_sha(),
        "recorded_at": _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)
                        .isoformat().replace("+00:00", "Z"),
        "inputs_path": str(inputs_path) if inputs_path is not None else None,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "versions": versions(*modules),
    }
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
