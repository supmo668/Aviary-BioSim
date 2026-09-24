"""Per-test fixtures for the science suite, and a guard against stub leakage.

The defect this file exists to close (F08): test modules used to install fake
modules into `sys.modules` at IMPORT time and never restore them. Import time is
collection time, which happens before any test runs, so the fakes were live for
the whole session. Which module a later `import esm_tool` resolved to then
depended on pytest's collection order, and one module imported another as a
library to borrow its stub. The symptom was two failures under
`--import-mode=importlib`; the real problem was that a green run proved nothing
about isolation, only that the ordering happened to be favourable.

Everything here is installed with `monkeypatch.setitem(sys.modules, ...)`, so it
is torn down after each test. Nothing is installed at import time.

Every fake carries `IS_TEST_STUB`, and `pytest_runtest_setup` / `_teardown` fail a
test that finds one in `sys.modules` outside the fixture that owns it. That guard
is the part that keeps this from decaying: without it, the next module to install
a global stub reintroduces the defect silently, which is exactly how it arrived.
"""
import importlib.util
import sys
import types
from pathlib import Path

import pytest

SCIENCE = Path(__file__).resolve().parents[1]
DEMO = SCIENCE.parent / "demo"

IS_TEST_STUB = "__aviary_test_stub__"
WATCHED = ("esm_tool", "torch", "transformers", "requests")


def _stub(name: str) -> types.ModuleType:
    module = types.ModuleType(name)
    setattr(module, IS_TEST_STUB, True)
    return module


def _leaked() -> list[str]:
    return [n for n in WATCHED
            if getattr(sys.modules.get(n), IS_TEST_STUB, False)]


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    """Before fixtures run: nothing may already be stubbed."""
    leaked = _leaked()
    if leaked:
        pytest.fail(
            f"test stub(s) {leaked} were in sys.modules BEFORE {item.name} ran. "
            "A stub outlived the test that installed it, so this test may be "
            "exercising a fake it never asked for."
        )


@pytest.hookimpl(trylast=True)
def pytest_runtest_teardown(item, nextitem):
    """After fixtures are torn down: nothing may still be stubbed."""
    leaked = _leaked()
    if leaked:
        pytest.fail(
            f"test stub(s) {leaked} were still in sys.modules AFTER {item.name}. "
            "Install fakes with monkeypatch.setitem(sys.modules, ...) so they "
            "unwind; a leaked stub silently reaches later tests."
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
    exec(compile(path.read_text(), str(path), "exec"), module.__dict__)
    return module


@pytest.fixture
def stub_contract():
    """The isolation contract, reachable without importing conftest by name.

    `from conftest import ...` fails under --import-mode=importlib, so the marker and
    the watched list are handed over as a fixture instead.
    """
    class Contract:
        marker = IS_TEST_STUB
        watched = WATCHED

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
        self.BudgetExceeded = sys.modules["spend_tracker"].BudgetExceeded
        self.ToolCall = sys.modules["aviary.core"].ToolCall
        self.ToolRequestMessage = sys.modules["aviary.core"].ToolRequestMessage

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
    sys.path.insert(0, str(DEMO)) if str(DEMO) not in sys.path else None
    import aviary.core  # noqa: F401  ensure the real package is resolvable
    import spend_tracker  # noqa: F401
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
