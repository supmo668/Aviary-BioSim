"""The agent-supplied accession must not reach the filesystem or the network unchecked.

esm_tool.fetch_sequence interpolates `accession` into BOTH a cache path
(CACHE/f"{accession}.json") and a UniProt URL. The agent chooses that string, so
a `../` value reads any .json on the host, and a value carrying `?`, `#` or a
path segment steers the request somewhere other than the intended entry.

torch, transformers and requests are stubbed: these tests load no model and make
no network call. The stubbed requests.get RAISES AssertionError, which pytest.raises
(ValueError) does not catch — that raise, not the ATTEMPTS list, is what fails a test
whose validation let a request through. ATTEMPTS is belt-and-braces and only becomes
load-bearing: no test in this file both installs a non-raising fake and asserts on
ATTEMPTS — the fetch test asserts on its own recorded URLs instead.
"""
import json
import sys
import types
from pathlib import Path

import pytest


def _stub_heavy_imports() -> list:
    """esm_tool imports torch/transformers at module scope and uses @torch.no_grad()."""
    attempts: list = []
    if "torch" not in sys.modules:
        torch = types.ModuleType("torch")
        torch.no_grad = lambda: (lambda fn: fn)
        backends = types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: False))
        torch.backends = backends
        torch.cuda = types.SimpleNamespace(is_available=lambda: False)
        sys.modules["torch"] = torch
    if "transformers" not in sys.modules:
        tf = types.ModuleType("transformers")
        tf.AutoTokenizer = object
        tf.AutoModelForMaskedLM = object
        sys.modules["transformers"] = tf
    req = types.ModuleType("requests")

    def _get(url, **kwargs):
        attempts.append(url)
        raise AssertionError(f"network reached with {url!r}; validation should have refused first")

    req.get = _get
    sys.modules["requests"] = req
    return attempts


PREV = {name: sys.modules.get(name) for name in ("requests", "torch", "transformers")}


ATTEMPTS = _stub_heavy_imports()


def _load_real_esm_tool():
    """Load science/esm_tool.py by PATH, under its own module name.

    A sibling test module installs a FAKE `esm_tool` in sys.modules for its own
    purposes, so `import esm_tool` here returns that stub or the real module
    depending on collection order. Loading by path removes the ordering question.
    """
    import importlib.util
    path = Path(__file__).resolve().parents[1] / "esm_tool.py"
    spec = importlib.util.spec_from_file_location("esm_tool_under_test", path)
    module = importlib.util.module_from_spec(spec)
    # exec the SOURCE rather than spec.loader.exec_module: the normal loader goes
    # through __pycache__, which is validated on (mtime-to-the-second, size). A
    # same-second, same-size edit therefore runs the PREVIOUS bytecode — which makes
    # mutation results silently wrong. Compiling here always reflects the file.
    exec(compile(path.read_text(), str(path), "exec"), module.__dict__)
    return module


esm_tool = _load_real_esm_tool()


@pytest.fixture(scope="module", autouse=True)
def _restore_requests_stub():
    """Unwind the sys.modules stubs after this module's tests.

    SCOPE, stated exactly: this removes the stubs before later test modules RUN. It
    does NOT protect the collection phase — pytest imports every test module before
    any test executes, so the stubs are live for that whole window, and a module that
    does `import requests` at module scope would bind the stub object permanently.
    Nothing in this suite does today (siblings use openai/weave/aviary.core), and a
    post-run sweep found no live reference to a stub. Moving the install into a
    conftest would close the window but make the stubs global to the session, which is
    the shape this file exists to avoid.

    The stubs must be installed at import time, before esm_tool is loaded, so they
    cannot live in a fixture — but they can be torn down in one. Without this they
    stay installed for the rest of the session, and a sibling test needing the real
    requests/torch/transformers silently gets a stub: `requests` with only `get`,
    `torch` with no `tensor`. That fails later with a confusing AttributeError
    instead of a missing-dependency error.
    """
    yield
    for name, previous in PREV.items():
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous

# Every accession the real experiment uses (science/run_experiment.py ORTHOLOGS).
REAL = ["P01308", "P01326", "P01322", "P01315", "P01317",
        "P01329", "P67970", "O73727", "P12706"]

# UniProt accessions are 6 OR 10 characters. Every entry above is 6, so without
# these the whole second branch of the grammar is unpinned: narrowing {1,2} to
# {1,1} refuses every modern TrEMBL accession and no test notices.
REAL_TEN_CHAR = ["A0A0B4J2D5", "A0A022YWF9", "A0A123BCD4"]

MALICIOUS = [
    "../../../etc/passwd",          # escape the cache directory
    "../seqs/P01308",               # escape and come back
    "P01308/../../../secret",       # traversal after a valid-looking prefix
    "/etc/hosts",                   # absolute path
    "..",                           # bare traversal
    "P01308?fields=all",            # steer the URL with a query
    "P01308#frag",                  # fragment
    "P01308/entry",                 # extra path segment
    "P01308%2f..%2fx",              # percent-encoded separator
    "P01308\n",                     # trailing newline
    "P01308 ",                      # trailing space
]

MALFORMED = ["", "   ", "p01308", "P0130", "ZZZZZZZZZZZZ", "P01308-1", "INS_HUMAN"]

# Uppercase-alphanumeric but NOT UniProt accessions. Harmless as paths, so a loose
# ^[A-Z0-9]{6,10}$ check accepts them; UniProt's own grammar does not. Pinned so the
# validator stays a grammar check rather than a character-class check: an accession
# that cannot exist should be refused here, not turned into a 404 or another entry.
NOT_ACCESSIONS = ["ZZZZZZ", "123456", "AAAAAAAAAA", "ABCDEF", "P0", "PPPPPP"]


@pytest.mark.parametrize("accession", NOT_ACCESSIONS)
def test_a_string_that_cannot_be_a_uniprot_accession_is_refused(accession):
    with pytest.raises(ValueError):
        esm_tool.valid_accession(accession)


@pytest.mark.parametrize("accession", REAL + REAL_TEN_CHAR)
def test_every_accession_the_experiment_actually_uses_is_accepted(accession):
    out = esm_tool.valid_accession(accession)
    assert out == accession
    assert type(out) is str


@pytest.mark.parametrize("accession", MALICIOUS + MALFORMED)
def test_a_bad_accession_is_refused(accession):
    with pytest.raises(ValueError):
        esm_tool.valid_accession(accession)


@pytest.mark.parametrize("accession", [None, 1, ["P01308"], {"a": 1}])
def test_a_non_string_accession_is_refused(accession):
    with pytest.raises(ValueError):
        esm_tool.valid_accession(accession)


@pytest.mark.parametrize("accession", MALICIOUS)
def test_fetch_sequence_refuses_before_touching_disk_or_network(accession, tmp_path, monkeypatch):
    monkeypatch.setattr(esm_tool, "CACHE", tmp_path / "seqs")
    ATTEMPTS.clear()
    with pytest.raises(ValueError):
        esm_tool.fetch_sequence(accession)
    assert ATTEMPTS == [], "validation must refuse before the request is made"
    assert not (tmp_path / "seqs").exists(), \
        "validation must refuse before the cache directory is created"


def test_a_traversal_cannot_read_a_json_file_outside_the_cache(tmp_path, monkeypatch):
    """The concrete exploit: a .json the agent should not be able to read."""
    secret = tmp_path / "secret.json"
    secret.write_text(json.dumps({"sequence": "MEOW", "length": 4}))
    cache = tmp_path / "seqs"
    cache.mkdir()
    monkeypatch.setattr(esm_tool, "CACHE", cache)
    with pytest.raises(ValueError):
        esm_tool.fetch_sequence("../secret")


def test_a_cached_valid_accession_is_still_served_from_disk(tmp_path, monkeypatch):
    cache = tmp_path / "seqs"
    cache.mkdir()
    rec = {"accession": "P01308", "name": "INS", "organism": "Homo sapiens",
           "sequence": "MALW", "length": 4}
    (cache / "P01308.json").write_text(json.dumps(rec))
    monkeypatch.setattr(esm_tool, "CACHE", cache)
    assert esm_tool.fetch_sequence("P01308") == rec


# --- Gate finding: isinstance() admits str SUBCLASSES, and returning the caller's
# object lets one override __format__ so the f-string builds a different path than
# the regex inspected. Not reachable through json.loads today; defence in depth.

class _Evil(str):
    """Passes the regex as its value, but formats as something else entirely."""

    def __format__(self, spec):  # noqa: D105
        return "../secret"

    def __str__(self):  # str() is not a fix either
        return "../secret"


def test_validation_returns_plain_text_not_the_callers_object():
    out = esm_tool.valid_accession(_Evil("P01308"))
    assert type(out) is str, type(out)
    assert f"{out}.json" == "P01308.json"


def test_a_str_subclass_cannot_steer_the_cache_path(tmp_path, monkeypatch):
    secret = tmp_path / "secret.json"
    secret.write_text(json.dumps({"sequence": "PWNED", "length": 5}))
    cache = tmp_path / "seqs"
    cache.mkdir()
    (cache / "P01308.json").write_text(json.dumps({"sequence": "REAL", "length": 4}))
    monkeypatch.setattr(esm_tool, "CACHE", cache)
    rec = esm_tool.fetch_sequence(_Evil("P01308"))
    assert rec["sequence"] == "REAL", "the formatted value, not the validated one, reached the path"


# --- Gate findings: the two tools the AGENT actually calls were never exercised,
# and the fetch/cache branch had no coverage at all.

@pytest.mark.parametrize("accession", MALICIOUS)
def test_the_agent_facing_tools_refuse_a_bad_accession(accession, tmp_path, monkeypatch):
    """score_variant and embed_sequence are what BioSimEnv offers the agent. Both
    must raise, not return an error string: they return strings on other failure
    paths, so a swallowed exception would read as success."""
    monkeypatch.setattr(esm_tool, "CACHE", tmp_path / "seqs")
    ATTEMPTS.clear()
    with pytest.raises(ValueError):
        esm_tool.score_variant(accession, 1, "A")
    with pytest.raises(ValueError):
        esm_tool.embed_sequence(accession)
    assert ATTEMPTS == []


def test_a_tool_call_cannot_read_a_secret_through_traversal(tmp_path, monkeypatch):
    secret = tmp_path / "secret.json"
    secret.write_text(json.dumps({"sequence": "PWNED", "name": "x",
                                  "organism": "x", "length": 5}))
    cache = tmp_path / "seqs"
    cache.mkdir()
    monkeypatch.setattr(esm_tool, "CACHE", cache)
    for call in (lambda: esm_tool.score_variant("../secret", 1, "A"),
                 lambda: esm_tool.embed_sequence("../secret")):
        with pytest.raises(ValueError) as refused:
            call()
        assert "PWNED" not in str(refused.value)


class _FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


@pytest.mark.parametrize("accession", ["P01308", "O73727", "A0A0B4J2D5"])
def test_a_valid_accession_is_fetched_from_the_right_url_and_cached(accession, tmp_path, monkeypatch):
    """The happy path: nothing previously reached it, because the module-level stub
    always raises. Pins that the VALIDATED value is the one that reaches the URL —
    parametrized, because a single accession cannot tell a correct URL from one
    hardcoded to that same accession.
    """
    cache = tmp_path / "seqs"
    monkeypatch.setattr(esm_tool, "CACHE", cache)
    urls: list = []

    def fake_get(url, **kwargs):
        urls.append(url)
        return _FakeResponse(
            f">sp|{accession}|INS_X Insulin OS=Homo sapiens OX=9606\nMALWMRLL\n")

    monkeypatch.setattr(esm_tool.requests, "get", fake_get)

    rec = esm_tool.fetch_sequence(accession)

    assert urls == [f"https://rest.uniprot.org/uniprotkb/{accession}.fasta"]
    assert rec["accession"] == accession
    assert rec["organism"] == "Homo sapiens"
    assert rec["sequence"] == "MALWMRLL"
    assert rec["length"] == 8

    written = cache / f"{accession}.json"
    assert written.exists(), "the fetched record must be cached"
    assert written.resolve().parent == cache.resolve()

    again = esm_tool.fetch_sequence(accession)
    assert again == rec
    assert len(urls) == 1, "a cached accession must not be re-fetched"


def test_the_tools_report_the_validated_accession_not_the_callers_object(tmp_path, monkeypatch):
    """Same residual class as the cache-path bypass: both tools interpolated the
    PARAMETER into the string handed back to the agent, so a str subclass could put
    ANSI escapes (or any text) into what the operator reads. Report rec['accession'],
    which came from the validated value."""
    cache = tmp_path / "seqs"
    cache.mkdir()
    (cache / "P01308.json").write_text(json.dumps(
        {"accession": "P01308", "name": "INS", "organism": "Homo sapiens",
         "sequence": "MALW", "length": 4}))
    monkeypatch.setattr(esm_tool, "CACHE", cache)
    out = esm_tool.score_variant(_Evil("P01308"), 99, "A")
    assert "../secret" not in out, out
    assert "P01308" in out, out


def _seed_cache(tmp_path, monkeypatch):
    cache = tmp_path / "seqs"
    cache.mkdir()
    (cache / "P01308.json").write_text(json.dumps(
        {"accession": "P01308", "name": "INS", "organism": "Homo sapiens",
         "sequence": "MALW", "length": 4}))
    monkeypatch.setattr(esm_tool, "CACHE", cache)
    return cache


def test_score_variant_reports_the_validated_accession_on_its_normal_path(tmp_path, monkeypatch):
    """The success branch, reachable only with the model stubbed — the 'position
    outside' branch alone does not pin it."""
    _seed_cache(tmp_path, monkeypatch)
    monkeypatch.setattr(esm_tool, "position_logprobs",
                        lambda seq: [{"logp": {a: -1.0 for a in esm_tool.AA}} for _ in seq])
    out = esm_tool.score_variant(_Evil("P01308"), 2, "G")
    assert "../secret" not in out, out
    assert out.startswith("P01308 A2G"), out


def test_embed_sequence_reports_the_validated_accession(tmp_path, monkeypatch):
    _seed_cache(tmp_path, monkeypatch)
    monkeypatch.setattr(esm_tool, "embed", lambda seq: [0.0] * 8)
    out = esm_tool.embed_sequence(_Evil("P01308"))
    assert "../secret" not in out, out
    assert out.startswith("P01308 (Homo sapiens, 4 aa)"), out
