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


# What a rebuild itself writes, and may therefore leave modified without making the run
# unpinned: `tree_clean` is a claim about the CODE that produced an evidence file, and a full
# rebuild writes these in sequence, so the first producer's output would otherwise make every
# later one refuse. Only files a producer WRITES are listed. taxonomy.csv and weave-count.json
# are hand-authored — no script produces them — so they are INPUTS and stay dirty (QG F2).
GENERATED = (
    "paper/evidence/science-input.json",
    "paper/evidence/science.json",
    "paper/evidence/agent-run.json",
    "paper/evidence/drain1-from-git.csv",
    "paper/evidence/drain1-from-git.provenance.json",
    "paper/evidence/drain1-record-check.json",
    "paper/evidence/drain1-rerun.json",
    "paper/evidence/plugin-tests.json",
    "paper/evidence/repo-tests.json",
    "paper/evidence/candidate-record/",
)


def _status_entries() -> list[tuple[str, str]]:
    """Every `git status` entry as (code, path), unquoted, excluding what a rebuild writes.

    `-z` turns off C-quoting (a path with a space or a non-ASCII character came back wrapped
    in quotes and so matched no prefix) and `--no-renames` stops git emitting `old -> new` as
    one entry — which the previous `ln[3:]` slicing prefix-tested whole, so renaming a file
    OUT of the evidence directory silently excluded a staged file elsewhere, and the run then
    recorded tree_clean true over a tree that did not contain it (QG F4).
    """
    out = subprocess.check_output(
        ["git", "status", "--porcelain", "-z", "--no-renames"], text=True, cwd=REPO)
    entries = [(e[:2], e[3:]) for e in out.split("\0") if e.strip()]
    return [(c, p) for c, p in entries if not _is_generated(p)]


def _is_generated(path: str) -> bool:
    """Exact match for a written file, prefix match only for a written DIRECTORY.

    A plain `startswith` over the file names also exempted anything sharing a prefix, so
    `…/science.json.bak` — a hand-made copy sitting in the tree — read as generated.
    """
    return any(path == g or (g.endswith("/") and path.startswith(g)) for g in GENERATED)


def dirty_paths() -> list[str]:
    """Every path git reports as modified, staged or untracked, except what a rebuild writes.

    This is the REFUSAL decision, so untracked files count: an uncommitted new module is
    exactly the state that makes a recorded commit fail to describe the code that ran.
    """
    return [p for _, p in _status_entries()]


def publishable_dirty() -> list[str]:
    """The dirty paths that may be WRITTEN INTO the evidence file, which ships publicly.

    Untracked filenames are deliberately reduced to a count: a working checkout routinely
    carries untracked scratch, credential and client-named files, and `redact()` cannot help
    because these paths are repository-relative (QG F11). The names of tracked files are
    already public, so those are listed, under the same cap the refusal message uses.
    """
    entries = _status_entries()
    tracked = sorted(p for c, p in entries if c != "??")
    untracked = sum(1 for c, _ in entries if c == "??")
    out = tracked[:10]
    if len(tracked) > 10:
        out.append(f"(+{len(tracked) - 10} more tracked)")
    if untracked:
        out.append(f"({untracked} untracked file(s), names withheld)")
    return out


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
    _TREE_CLEAN, _DIRTY = not paths, (publishable_dirty() if paths else [])
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
# "keep only the last component" — the path may contain spaces (macOS home directories
# routinely do), so only the separator and the quote characters end a component (QG F12b).
_OTHER_HOME = re.compile(r"~/(?:[^/\"']+/)+(?P<base>[^/\s\"']+)")


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
        # The prefix passes above only catch a path that STARTS a string or is followed by a
        # separator. This sanitiser also runs over text captured from external tools
        # (referee stderr, the register's output), where the home path can be followed by a
        # space, a quote, a colon or end-of-string — and was then published verbatim (QG F12).
        for prefix, token in ((repo, "<repo>"), (parent, "<parent-project>"), (home, "~")):
            s = re.sub(re.escape(prefix) + r"(?![\w/])", token, s)
        s = _PLUGIN_CACHE.sub(lambda m: f"<plugin:{m['name']} {m['ver']}>", s)
        s = _OTHER_HOME.sub(lambda m: f"~/…/{m['base']}", s)
        # Refuse to hand back a string that still names the machine. Writing it is worse than
        # failing: the repository is public and a deposit is not retractable.
        if str(HOME) in s or "/Users/" in s or "/home/" in s:
            raise RuntimeError(f"redact() left a home path in a value it was asked to publish: {s[:120]!r}")
        return s
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def block(inputs_path: str | Path | None, extra: dict | None = None,
          modules: tuple[str, ...] = ()) -> dict:
    # Fail CLOSED when the guard never ran. The old default recomputed here, and by this
    # point the script has written its own (exempt) evidence, so it almost always evaluated
    # to true — a producer that forgot require_clean_tree() still published `tree_clean:
    # true`, asserting a guarantee whose check never executed (QG F3). That is the exact
    # shape this field exists to rule out, so it is an error rather than a default.
    if _TREE_CLEAN is None:
        raise RuntimeError(
            "provenance.block() called without require_clean_tree(): tree_clean would assert "
            "a guarantee that was never checked. Call require_clean_tree() first.")
    clean = _TREE_CLEAN
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
        b["dirty_paths"] = list(_DIRTY)   # the pre-run list, never a re-sample (QG F17)
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
