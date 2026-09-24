"""The agent-supplied accession must not reach the filesystem or the network unchecked.

esm_tool.fetch_sequence interpolates `accession` into BOTH a cache path
(CACHE/f"{accession}.json") and a UniProt URL. The agent chooses that string, so
a `../` value reads any .json on the host, and a value carrying `?`, `#` or a
path segment steers the request somewhere other than the intended entry.

torch, transformers and requests are stubbed: these tests load no model and make
no network call. If validation is missing, the stubbed requests.get records the
attempt and the test fails on that.
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
    spec.loader.exec_module(module)
    return module


esm_tool = _load_real_esm_tool()

# Every accession the real experiment uses (science/run_experiment.py ORTHOLOGS).
REAL = ["P01308", "P01326", "P01322", "P01315", "P01317",
        "P01329", "P67970", "O73727", "P12706"]

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


@pytest.mark.parametrize("accession", REAL)
def test_every_accession_the_experiment_actually_uses_is_accepted(accession):
    assert esm_tool.valid_accession(accession) == accession


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
