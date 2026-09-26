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
import importlib
import importlib.util
import pathlib
import sys
import types

import pytest

SCIENCE = pathlib.Path(__file__).resolve().parents[1]
DEMO = SCIENCE.parent / "demo"

# Names a fixture here swaps, plus the third-party names the modules under test
# import for real. THIS LIST IS THE GUARD'S ENTIRE REACH: a fake under any other name
# is invisible. Add the name when you add the import.
# Imported HERE, before collection, so the baseline holds the real module OBJECT and the
# check is pure identity. These are the names this suite genuinely resolves for real
# during a run: the `disc` fixture executes run_discovery.py by path (which imports
# openai and weave), `bio` uses spend_tracker, and aviary.core supplies Environment/Tool.
# Every name here must be a DECLARED dependency of the invocation, not one that happens
# to arrive transitively. `requests` was undeclared for months and the suite was green
# only because openai/weave pulled it in; when that resolution changed, three tests went
# red. That is the same defect as depending on whether torch is installed — the suite's
# colour becoming a property of the machine — and it is exactly what
# test_no_preimported_name_failed_to_import exists to make loud instead of silent.
PREIMPORT = ("yaml", "requests", "openai", "weave",
             "aviary", "aviary.core", "spend_tracker")

# Watched, but deliberately NOT imported here.
#   esm_tool / biosim_env / run_discovery are the modules under test. Importing them runs
#   production code during collection: run_discovery's module body builds an openai client
#   from os.environ["WANDB_API_KEY"], so on a fully-provisioned machine merely collecting
#   this suite either raised KeyError or opened a live API client. They also bought ZERO
#   baseline entries, because all three need torch.
#   torch / transformers are heavy dependencies this suite always stubs.
# Whatever sys.modules holds for these when the snapshot is taken IS their baseline, so a
# transitive import (weave can pull torch on a machine that has it) is recorded rather
# than treated as a leak for the rest of the session.
DEFERRED = ("esm_tool", "biosim_env", "run_discovery", "torch", "transformers")

WATCHED = PREIMPORT + DEFERRED

# The module OBJECT each watched name held before collection, or None if the name was
# absent. Identity is the whole check.
_BASELINE: dict = {}
# Only this project's own directories. Other suites in the same session add their own
# entries and those are none of this plugin's business.
_OURS = ()


def pytest_configure(config):
    """Snapshot the real world before collection imports any test module.

    Every PREIMPORT name is imported here, so the baseline holds the genuine module
    object and the check becomes `sys.modules[name] is the object we recorded` — the one
    thing a fake cannot forge. Earlier versions authenticated a module from its own
    __file__, then its __spec__.origin; both are attributes the impostor sets, and both
    were defeated by a three-line fake.

    Third-party names resolve with nothing of ours on sys.path. Two things put project
    directories there before this hook runs: pytest's prepend import mode inserts THIS
    conftest's directory when it loads it, and `python -m pytest` adds the working
    directory. An earlier version also prepended science/ and demo/ itself. Through any of
    those, a file named yaml.py in the project would be executed and recorded as the
    genuine baseline — with _repair() faithfully reinstalling it after every test. The
    guard poisoning its own ground truth. So the loop below runs on sys.path with the
    working directory, the rootdir, the invocation directory, this directory, science/
    and demo/ removed, and restores the full path afterwards. Pinned by
    test_a_shadow_beside_the_conftest_is_not_recorded_as_the_baseline.

    A DEFERRED name is not imported and usually stays absent, so any appearance is
    reported. That is stricter, not weaker. Import failures are recorded rather than
    swallowed, because a name that silently stops importing downgrades its own check from
    identity to presence, and a green suite would never say so.

    Cost, measured rather than guessed: about 0.6 s in a cold process, essentially all of
    it weave, openai and aviary.core. Dropping the three project modules did NOT make this
    cheaper — their cost was almost entirely the same third-party imports, pulled in
    transitively — so the justification here is correctness, not speed. An earlier comment
    blamed spend_tracker pulling in yaml; those are ~6 ms and ~0 ms respectively. Note also
    that this suite spawns 17 pytester subprocesses, each of which pays it again.
    """
    global _OURS
    _OURS = (str(SCIENCE), str(DEMO))
    failures = {}
    saved = list(sys.path)
    not_ours = _project_free(sys.path, config)
    try:
        sys.path[:] = not_ours
        for name in PREIMPORT:
            if name == "spend_tracker":
                continue                  # lives in demo/, needs the path; done below
            try:
                importlib.import_module(name)
            except Exception as exc:
                failures[name] = f"{type(exc).__name__}: {exc}"
        sys.path[:] = [str(DEMO)] + not_ours
        try:
            importlib.import_module("spend_tracker")
        except Exception as exc:
            failures["spend_tracker"] = f"{type(exc).__name__}: {exc}"
    finally:
        sys.path[:] = saved
    _BASELINE.clear()
    _BASELINE.update({name: sys.modules.get(name) for name in WATCHED})
    _BASELINE_SYSPATH[:] = list(sys.path)
    _IMPORT_FAILURES.clear()
    _IMPORT_FAILURES.update(failures)


def _project_free(path: list, config) -> list:
    """sys.path with every entry that could shadow a third-party name removed.

    "" and "." mean the working directory; rootpath and the invocation dir are where
    pytest was pointed; this conftest's directory is what prepend mode inserted.
    Compared by resolved path so a relative spelling cannot slip through.
    """
    here = pathlib.Path(__file__).resolve().parent
    ours = {here, SCIENCE, DEMO, pathlib.Path.cwd().resolve(),
            pathlib.Path(config.rootpath).resolve(),
            pathlib.Path(config.invocation_params.dir).resolve()}
    return [entry for entry in path
            if entry not in ("", ".") and pathlib.Path(entry).resolve() not in ours]


_BASELINE_SYSPATH: list = []
# PREIMPORT names that did NOT import, and why. Empty is the healthy state.
_IMPORT_FAILURES: dict = {}


def _stub(name: str) -> types.ModuleType:
    return types.ModuleType(name)


def _is_baseline(name: str) -> bool:
    """Is this name still bound to the exact object recorded before collection?"""
    return sys.modules.get(name) is _BASELINE.get(name)


def _leaked() -> list:
    """Watched names whose sys.modules entry is not the object recorded at configure.

    No attribute is consulted. A forged __file__, a forged __spec__.origin, a spec
    claiming to be a package, a sourceless .pyc, a zip import — none of them change the
    fact that the object is not the one that was there before collection.

    What this does NOT see is in-place mutation: `import yaml; yaml.safe_load = evil`
    leaves the object identical, so no hook fires and _repair cannot undo it. Identity
    authenticates the binding, not the contents. Recorded in docs/deferred-findings.md.

    The comparison lives in _is_baseline so the mutation catalogue can anchor on a line
    of CODE. Three entries used to anchor on this function's return statement and on the
    prose above it, which meant rewording a comment turned the anti-rot test red.
    """
    return [name for name in WATCHED if not _is_baseline(name)]


def _path_leaks() -> list:
    """This project's own directories, left on sys.path by something that did not unwind.

    Deliberately narrow. A fixture that forgets monkeypatch.syspath_prepend is a real
    defect and this catches it; another suite's sys.path entries are not this plugin's
    to police, and treating them as leaks once aborted whole sessions over other
    people's code. Shadowing is no longer a concern here: every watched name is already
    imported at configure, so a later path entry cannot change what it resolves to.
    """
    baseline = set(_BASELINE_SYSPATH)
    return [entry for entry in _OURS if entry in sys.path and entry not in baseline]


def _repair() -> None:
    """Put the world back, so ONE leak fails ONE test instead of every test after it."""
    for name in WATCHED:
        base = _BASELINE.get(name)
        if base is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = base
    for entry in _path_leaks():
        while entry in sys.path:
            sys.path.remove(entry)


def _describe(leaked, paths) -> str:
    return (f"sys.modules: {leaked or 'clean'}; "
            f"stray {SCIENCE.name}/{DEMO.name} sys.path entries: {paths or 'none'}")


def pytest_collection_finish(session):
    """Report an import-time write HERE, where it is attributable.

    Collection is what imports test modules, so a module that writes sys.modules at
    import time has already done it before any test runs. Blaming the first test to run
    marks an innocent file red.
    """
    leaked, paths = _leaked(), _path_leaks()
    if leaked or paths:
        _repair()
        raise pytest.UsageError(
            "a test module changed global import state while being COLLECTED — "
            f"{_describe(leaked, paths)}. The offender is a module imported during "
            "collection, not the first test that runs. Never assign sys.modules or "
            "sys.path from a test module: ask for a fixture (esm_stub / esm / bio / "
            "disc), or add one to conftest."
        )


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    """Before fixtures run: global import state must match the pre-collection snapshot."""
    leaked, paths = _leaked(), _path_leaks()
    if leaked or paths:
        _repair()
        pytest.fail(
            f"{item.nodeid} ran with global import state already dirty — "
            f"{_describe(leaked, paths)}. This test is the one that NOTICED it, not "
            "necessarily the one that caused it: an earlier test, or a plugin, could "
            "have. Ask for a fixture (esm_stub / esm / bio / disc) or add one here."
        )


@pytest.hookimpl(trylast=True)
def pytest_runtest_teardown(item, nextitem):
    """After fixtures are torn down: nothing may still be replaced."""
    leaked, paths = _leaked(), _path_leaks()
    if leaked or paths:
        _repair()
        pytest.fail(
            f"{item.nodeid} left global import state dirty — {_describe(leaked, paths)}. "
            "Install fakes with monkeypatch.setitem(sys.modules, ...) and paths with "
            "monkeypatch.syspath_prepend(...) so they unwind."
        )


def _load_by_path(name: str, path: pathlib.Path) -> types.ModuleType:
    """Load a module from source under `name`, bypassing __pycache__.

    exec'ing the compiled source rather than using spec.loader.exec_module: the
    bytecode cache validates on (mtime-to-the-second, size), so a same-second
    same-size edit runs the PREVIOUS version — which makes mutation testing report
    the wrong answer while the file on disk is correct.

    Each call returns a DISTINCT module object. Anything that must share class
    identity with another fixture's module has to be pinned into sys.modules (see
    `disc`) or imported normally (see spend_tracker in _Bio).
    """
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    saved_for_loader = list(sys.path)
    try:
        # The modules under test insert their own directories into sys.path at import.
        # Unwound here: otherwise every test grows the path, and a later bare import
        # resolves differently depending on what ran first — the same order-dependence
        # this file exists to remove, moved from sys.modules into sys.path.
        #
        # NOT redundant: the `esm` fixture calls this loader without ever calling
        # monkeypatch.syspath_prepend, so no monkeypatch snapshot of sys.path exists
        # for it and this `finally` is the only thing unwinding a sys.path write by the
        # module it loads. test_load_by_path_restores_sys_path pins it directly.
        exec(compile(path.read_text(), str(path), "exec"), module.__dict__)
    finally:
        sys.path[:] = saved_for_loader
    return module


@pytest.fixture
def stub_contract():
    """The isolation contract, reachable without importing conftest by name.

    `from conftest import ...` fails under --import-mode=importlib, so the pieces the
    contract tests need are handed over as a fixture instead.
    """
    class Contract:
        watched = WATCHED
        science_dir = str(SCIENCE)
        demo_dir = str(DEMO)
        load_by_path = staticmethod(_load_by_path)
        bio_class = _Bio
        runtest_setup = staticmethod(pytest_runtest_setup)
        path_leaks = staticmethod(_path_leaks)
        repair = staticmethod(_repair)
        preimport = PREIMPORT
        import_failures = _IMPORT_FAILURES
        baseline = _BASELINE

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

    def score_variant(accession: str, position: int, mutant: str) -> str:
        """Score a substitution.

        The parameter list must match science/esm_tool.score_variant exactly:
        BioSimEnv.reset builds the agent's tool schema with Tool.from_function on
        whatever sys.modules holds, so a stub with a different shape means the budget
        tests measure a tool that cannot exist in production. Pinned by
        test_the_stub_tool_has_the_same_signature_as_the_real_one.

        Args:
            accession: Database accession.
            position: 1-based residue position.
            mutant: The substituted residue, one of the 20 amino acids.
        """
        calls.append(f"score_variant:{position}{mutant}")
        return "-1.25"      # a str, like production; the harness str()s it anyway

    def embed_sequence(accession: str) -> str:
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
