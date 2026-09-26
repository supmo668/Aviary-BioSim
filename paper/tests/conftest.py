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
    return module


@pytest.fixture
def prov():
    """The shared provenance block, freshly loaded."""
    return load_script("_provenance")


@pytest.fixture
def script(monkeypatch):
    """Load a script by name; `_provenance`, which scripts import by bare name, is
    removed from sys.modules afterwards so no test sees another's copy."""
    monkeypatch.delitem(sys.modules, "_provenance", raising=False)

    def _load(name: str):
        return load_script(name)

    return _load
