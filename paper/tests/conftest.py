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


def load_script(name: str):
    """Load paper/scripts/<name>.py from source under a test-private module name."""
    spec = importlib.util.spec_from_file_location(f"paper_script_{name}", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def prov():
    """The shared provenance block, freshly loaded."""
    return load_script("_provenance")
