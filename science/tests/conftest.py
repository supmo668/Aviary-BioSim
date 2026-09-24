"""Per-test fixtures for the science suite, and a guard against stub leakage.

The defect this file exists to close (F08): test modules used to install fake
modules into `sys.modules` at IMPORT time and never restore them. Import time is
collection time, which happens before any test runs, so the fakes were live for
the whole session. Which module a later `import esm_tool` resolved to then
depended on pytest's collection order, and one module imported another as a
library to borrow its stub. The symptom was two failures under
`--import-mode=importlib`; the real problem was that a green run proved nothing
about isolation, only that the ordering happened to be favourable.

Fakes are installed with `monkeypatch.setitem(sys.modules, ...)` and `sys.path` is
restored around every by-path load, so both unwind after each test.

RULE FOR TEST MODULES: never assign `sys.modules` yourself. Ask for a fixture
(`esm_stub`, `esm`, `bio`, `disc`) or add one here. An import-time write to any
watched name fails the run.

That rule is enforced, not merely stated. `pytest_configure` snapshots what each
watched name held before collection, and the setup/teardown hooks fail a test whose
`sys.modules` no longer matches. The check is by IDENTITY rather than by a marker,
because a marker would only catch fakes written here — and the contributor who
reintroduces this defect will write a plain ModuleType and never have heard of it.
"""
import importlib.util
import sys
import types
from pathlib import Path

import pytest

SCIENCE = Path(__file__).resolve().parents[1]
DEMO = SCIENCE.parent / "demo"

IS_TEST_STUB = "__aviary_test_stub__"

# Every name a fixture here swaps, plus every name the modules under test import for
# real. A name missing from this list is a name the guard cannot see.
WATCHED = ("esm_tool", "biosim_env", "run_discovery", "spend_tracker",
           "aviary.core", "torch", "transformers", "requests")

# What sys.modules held for each watched name BEFORE collection imported anything.
_BASELINE: dict = {}
_BASELINE_SYSPATH: list = []


def pytest_configure(config):
    """Snapshot the real world before any test module is imported.

    Collection imports every test module before the first test runs, so this has to
    happen at configure time: a module that installs a fake at import time has
    already done so by the time any fixture or hook for a test runs.
    """
    _BASELINE.clear()
    _BASELINE.update({n: sys.modules.get(n) for n in WATCHED})
    _BASELINE_SYSPATH[:] = list(sys.path)


def _stub(name: str) -> types.ModuleType:
    module = types.ModuleType(name)
    setattr(module, IS_TEST_STUB, True)
    return module


def _leaked() -> list:
    """Watched names whose entry is not what it was before collection.

    Deliberately IDENTITY-based, not marker-based. A marker only finds fakes this
    file created, which is the one population that cannot cause the defect — the
    contributor who reintroduces it will write a plain ModuleType and never hear of
    the marker. Identity finds theirs too.

    A name that was absent at baseline and is now a real importable module (it has a
    __file__) is not a leak: the suite legitimately imports aviary.core, requests and
    others as it runs.
    """
    out = []
    for name in WATCHED:
        current, base = sys.modules.get(name), _BASELINE.get(name)
        if base is not None:
            if current is not base:
                out.append(name)
        elif current is not None and getattr(current, "__file__", None) is None:
            out.append(name)
    return out


def _repair() -> None:
    """Put the watched names back, so ONE leak fails ONE test.

    Without this a single leaked module fails every test after it, and the offender
    is buried under hundreds of identical errors.
    """
    for name in WATCHED:
        base = _BASELINE.get(name)
        if base is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = base
    sys.path[:] = list(_BASELINE_SYSPATH)


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    """Before fixtures run: sys.modules must look like it did before collection."""
    leaked = _leaked()
    if leaked:
        _repair()
        pytest.fail(
            f"{item.nodeid}: {leaked} was replaced in sys.modules before this test ran. "
            "Either a test module wrote sys.modules at import/collection time, or an "
            "earlier test leaked. Ask for a fixture (esm_stub / esm / bio / disc) or add "
            "one here; never assign sys.modules from a test module."
        )


@pytest.hookimpl(trylast=True)
def pytest_runtest_teardown(item, nextitem):
    """After fixtures are torn down: nothing may still be replaced."""
    leaked = _leaked()
    if leaked:
        _repair()
        pytest.fail(
            f"{item.nodeid} left {leaked} replaced in sys.modules. Install fakes with "
            "monkeypatch.setitem(sys.modules, ...) so they unwind."
        )


def _load_by_path(name: str, path: Path) -> types.ModuleType:
    """Load a module from source under `name`, bypassing __pycache__.

    exec'ing the compiled source rather than using spec.loader.exec_module: the
    bytecode cache validates on (mtime-to-the-second, size), so a same-second
    same-size edit runs the PREVIOUS version — which makes mutation testing report
    the wrong answer while the file on disk is correct.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    saved = list(sys.path)
    try:
        # The modules under test insert their own directories into sys.path at import.
        # Unwound here: otherwise every test grows the path, and a later bare import
        # resolves differently depending on what ran first — the same order-dependence
        # this file exists to remove, moved from sys.modules into sys.path.
        #
        # Redundant TODAY, and deliberately kept: monkeypatch.syspath_prepend restores
        # the whole sys.path list on undo, so the fixtures already cover this and no
        # test can distinguish its removal. It is here for the fixture that forgets to
        # use monkeypatch — which is how this defect arrived the first time.
        exec(compile(path.read_text(), str(path), "exec"), module.__dict__)
    finally:
        sys.path[:] = saved
    return module

    # NOTE: each call returns a DISTINCT module object. Anything that must share class
    # identity with another fixture's module has to be pinned into sys.modules (see
    # `disc`) or imported normally (see spend_tracker in _Bio).


@pytest.fixture
def stub_contract():
    """The isolation contract, reachable without importing conftest by name.

    `from conftest import ...` fails under --import-mode=importlib, so the marker and
    the watched list are handed over as a fixture instead.
    """
    class Contract:
        marker = IS_TEST_STUB
        watched = WATCHED
        science_dir = str(SCIENCE)
        demo_dir = str(DEMO)

        @staticmethod
        def stubbed() -> list:
            return _leaked()

    return Contract


# --- the fake protein-model tool -------------------------------------------------

@pytest.fixture
def esm_stub(monkeypatch):
    """A fake `esm_tool`, recording its calls. Never loads a model."""
    calls: list[str] = []
    module = _stub("esm_tool")

    def score_variant(accession: str, mutation: str) -> float:
        """Score a substitution.

        Args:
            accession: Database accession.
            mutation: Substitution such as A12G.
        """
        calls.append(f"score_variant:{mutation}")
        return -1.25

    def embed_sequence(accession: str) -> int:
        """Embed a sequence.

        Args:
            accession: Database accession.
        """
        calls.append("embed_sequence")
        raise ValueError("instrument fault")

    module.score_variant = score_variant
    module.embed_sequence = embed_sequence
    module.calls = calls
    monkeypatch.setitem(sys.modules, "esm_tool", module)
    return module


class _Bio:
    """Bundle handed to the environment tests: module, helpers, recorder."""

    def __init__(self, module, calls):
        self.module = module
        self.calls = calls
        # Imported, not read out of sys.modules: the import system caches, so these are
        # the same objects the code under test raises and constructs, without depending
        # on another function having imported them first.
        from aviary.core import ToolCall, ToolRequestMessage
        from spend_tracker import BudgetExceeded

        self.BudgetExceeded = BudgetExceeded
        self.ToolCall = ToolCall
        self.ToolRequestMessage = ToolRequestMessage

    def env(self, ceiling: float = 1.0, max_rounds: int = 10):
        import asyncio
        self.calls.clear()
        env = self.module.BioSimEnv("objective", ceiling_usd=ceiling, max_rounds=max_rounds)
        asyncio.run(env.reset())
        return env

    def step(self, env, *calls):
        import asyncio
        action = self.ToolRequestMessage(content=None, tool_calls=[
            self.ToolCall.from_name(name, **args) for name, args in calls])
        return asyncio.run(env.step(action))


@pytest.fixture
def bio(esm_stub, monkeypatch):
    """`biosim_env` loaded against the fake tool, with env/step helpers."""
    monkeypatch.syspath_prepend(str(DEMO))
    module = _load_by_path("biosim_env_under_test", SCIENCE / "biosim_env.py")
    return _Bio(module, esm_stub.calls)


# --- the real protein-model tool, with its heavy imports faked -------------------

@pytest.fixture
def esm(monkeypatch):
    """The REAL `esm_tool`, with torch/transformers/requests faked.

    Loads no model and makes no network call: the fake `requests.get` raises, so a
    test whose validation let a request through fails on that raise.
    """
    torch = _stub("torch")
    torch.no_grad = lambda: (lambda fn: fn)
    torch.backends = types.SimpleNamespace(
        mps=types.SimpleNamespace(is_available=lambda: False))
    torch.cuda = types.SimpleNamespace(is_available=lambda: False)

    transformers = _stub("transformers")
    transformers.AutoTokenizer = object
    transformers.AutoModelForMaskedLM = object

    attempts: list[str] = []
    requests = _stub("requests")

    def _get(url, **kwargs):
        attempts.append(url)
        raise AssertionError(
            f"network reached with {url!r}; validation should have refused first")

    requests.get = _get

    for name, module in (("torch", torch), ("transformers", transformers),
                         ("requests", requests)):
        monkeypatch.setitem(sys.modules, name, module)

    module = _load_by_path("esm_tool_under_test", SCIENCE / "esm_tool.py")
    module.attempts = attempts
    return module


# --- the discovery harness --------------------------------------------------------

@pytest.fixture
def disc(bio, monkeypatch):
    """`run_discovery` loaded against the fake tool."""
    monkeypatch.setenv("WANDB_API_KEY", "test-not-a-real-key")
    monkeypatch.syspath_prepend(str(SCIENCE))
    monkeypatch.setitem(sys.modules, "biosim_env", bio.module)
    module = _load_by_path("run_discovery_under_test", SCIENCE / "run_discovery.py")
    module.bio = bio
    return module
