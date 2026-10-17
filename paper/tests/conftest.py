"""Fixtures for the white-paper scripts' tests.

The scripts under paper/scripts/ are run as `uv run --script` programs and locate
`_provenance` by inserting their own directory on sys.path at RUN time. The tests do
not copy that at IMPORT time — an import-time sys.path write is the shape
science/tests/conftest.py exists to forbid — and instead load each script by path
inside a fixture, so nothing leaks between tests.
"""
import importlib.util
import pathlib

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"


import sys


def load_script(name: str):
    """Load paper/scripts/<name>.py from source under a test-private module name.

    The scripts insert their own directory on sys.path when they run (so `import
    _provenance` resolves); that write is unwound here so it does not outlive the load.
    """
    saved = list(sys.path)
    try:
        spec = importlib.util.spec_from_file_location(f"paper_script_{name}", SCRIPTS / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = saved
        # The script's own `import _provenance` registers it in sys.modules, where it then
        # outlived the test: a stubbed dirty_paths and a cached _TREE_CLEAN leaked into every
        # later loader, and a test that arranged NOTHING passed a dirty-tree assertion
        # (QG F9). The module object each caller gets is reached through `module.P`, so
        # dropping the global entry here costs nothing.
        sys.modules.pop("_provenance", None)
    return module


@pytest.fixture
def prov():
    """The shared provenance block, freshly loaded."""
    return load_script("_provenance")


@pytest.fixture(autouse=True, scope="session")
def _never_write_bytecode_into_the_repository():
    """This suite exec-loads scripts by path, and one of them lives inside a DEPOSIT
    artifact directory (`paper/figures/make_figures.py`). Importing it writes a `.pyc`
    beside it, and that `.pyc` embeds the machine's username and full worktree path in
    `co_filename` — which is how a PII leak reached the declared publication payload, and
    how it came back after being deleted. It regenerates on any run without `-B`, so the
    guard belongs here rather than in a one-off cleanup.
    """
    saved = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    yield
    sys.dont_write_bytecode = saved


@pytest.fixture(autouse=True)
def _no_leaked_provenance():
    """`_provenance` must not survive a test. It is imported by bare name inside every
    script, so a stubbed `dirty_paths` or a cached `_TREE_CLEAN` left in sys.modules reached
    every later test and made dirty-tree assertions pass with no arrangement at all (QG F9).
    """
    sys.modules.pop("_provenance", None)
    yield
    assert "_provenance" not in sys.modules, "a test leaked _provenance into sys.modules"


@pytest.fixture
def script(monkeypatch):
    """Load a script by name, with the tree-state guard neutralised for that script's own
    `_provenance` instance only."""

    def _load(name: str):
        mod = load_script(name)
        # Every producer refuses a dirty tree (A7-2), and the tree IS dirty whenever the
        # suite runs over uncommitted work. These tests are about the scripts' own
        # behaviour, so they run as if the tree were clean; that the refusal is wired up at
        # all is asserted separately, per script, in test_scripts.py.
        # monkeypatch, not a raw assignment: the module object is shared with anything else
        # holding a reference, and a raw write outlived the test (QG F9).
        if hasattr(mod, "P"):
            monkeypatch.setattr(mod.P, "dirty_paths", lambda: [])
            monkeypatch.setattr(mod.P, "_TREE_CLEAN", None)
            monkeypatch.setattr(mod.P, "_DIRTY", [])
        return mod

    return _load
