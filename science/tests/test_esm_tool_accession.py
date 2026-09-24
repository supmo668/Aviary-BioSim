"""The agent-supplied accession must not reach the filesystem or the network unchecked.

esm_tool.fetch_sequence interpolates `accession` into BOTH a cache path
(CACHE/f"{accession}.json") and a UniProt URL. The agent chooses that string, so a
`../` value reads any .json on the host, and a value carrying `?`, `#` or a path
segment steers the request somewhere other than the intended entry.

The `esm` fixture (conftest.py) loads the real module with torch, transformers and
requests faked per test: no model is loaded and no network call is made. The fake
requests.get RAISES, and that raise — not the recorded-attempts list — is what fails
a test whose validation let a request through.
"""
import json

import pytest


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

MALFORMED = ["", "   ", "p01308", "P0130", "ZZZZZZZZZZZZ", "P01308-1", "ABCD_WXYZ"]

# Uppercase-alphanumeric but NOT UniProt accessions. Harmless as paths, so a loose
# ^[A-Z0-9]{6,10}$ check accepts them; UniProt's own grammar does not. Pinned so the
# validator stays a grammar check rather than a character-class check: an accession
# that cannot exist should be refused here, not turned into a 404 or another entry.
NOT_ACCESSIONS = ["ZZZZZZ", "123456", "AAAAAAAAAA", "ABCDEF", "P0", "PPPPPP"]


@pytest.mark.parametrize("accession", NOT_ACCESSIONS)
def test_a_string_that_cannot_be_a_uniprot_accession_is_refused(esm, accession):
    with pytest.raises(ValueError):
        esm.valid_accession(accession)


@pytest.mark.parametrize("accession", REAL + REAL_TEN_CHAR)
def test_every_accession_the_experiment_actually_uses_is_accepted(esm, accession):
    out = esm.valid_accession(accession)
    assert out == accession
    assert type(out) is str


@pytest.mark.parametrize("accession", MALICIOUS + MALFORMED)
def test_a_bad_accession_is_refused(esm, accession):
    with pytest.raises(ValueError):
        esm.valid_accession(accession)


@pytest.mark.parametrize("accession", [None, 1, ["P01308"], {"a": 1}])
def test_a_non_string_accession_is_refused(esm, accession):
    with pytest.raises(ValueError):
        esm.valid_accession(accession)


@pytest.mark.parametrize("accession", MALICIOUS)
def test_fetch_sequence_refuses_before_touching_disk_or_network(esm, accession, tmp_path, monkeypatch):
    monkeypatch.setattr(esm, "CACHE", tmp_path / "seqs")
    esm.attempts.clear()
    with pytest.raises(ValueError):
        esm.fetch_sequence(accession)
    assert esm.attempts == [], "validation must refuse before the request is made"
    assert not (tmp_path / "seqs").exists(), \
        "validation must refuse before the cache directory is created"


def test_a_traversal_cannot_read_a_json_file_outside_the_cache(esm, tmp_path, monkeypatch):
    """The concrete exploit: a .json the agent should not be able to read."""
    secret = tmp_path / "secret.json"
    secret.write_text(json.dumps({"sequence": "MEOW", "length": 4}))
    cache = tmp_path / "seqs"
    cache.mkdir()
    monkeypatch.setattr(esm, "CACHE", cache)
    with pytest.raises(ValueError):
        esm.fetch_sequence("../secret")


def test_a_cached_valid_accession_is_still_served_from_disk(esm, tmp_path, monkeypatch):
    cache = tmp_path / "seqs"
    cache.mkdir()
    rec = {"accession": "P01308", "name": "EXMP", "organism": "Testus fictus",
           "sequence": "MALW", "length": 4}
    (cache / "P01308.json").write_text(json.dumps(rec))
    monkeypatch.setattr(esm, "CACHE", cache)
    assert esm.fetch_sequence("P01308") == rec


# --- Gate finding: isinstance() admits str SUBCLASSES, and returning the caller's
# object lets one override __format__ so the f-string builds a different path than
# the regex inspected. Not reachable through json.loads today; defence in depth.

class _Evil(str):
    """Passes the regex as its value, but formats as something else entirely."""

    def __format__(self, spec):  # noqa: D105
        return "../secret"

    def __str__(self):  # str() is not a fix either
        return "../secret"


def test_validation_returns_plain_text_not_the_callers_object(esm):
    out = esm.valid_accession(_Evil("P01308"))
    assert type(out) is str, type(out)
    assert f"{out}.json" == "P01308.json"


def test_a_str_subclass_cannot_steer_the_cache_path(esm, tmp_path, monkeypatch):
    secret = tmp_path / "secret.json"
    secret.write_text(json.dumps({"sequence": "PWNED", "length": 5}))
    cache = tmp_path / "seqs"
    cache.mkdir()
    (cache / "P01308.json").write_text(json.dumps({"sequence": "REAL", "length": 4}))
    monkeypatch.setattr(esm, "CACHE", cache)
    rec = esm.fetch_sequence(_Evil("P01308"))
    assert rec["sequence"] == "REAL", "the formatted value, not the validated one, reached the path"


# --- Gate findings: the two tools the AGENT actually calls were never exercised,
# and the fetch/cache branch had no coverage at all.

@pytest.mark.parametrize("accession", MALICIOUS)
def test_the_agent_facing_tools_refuse_a_bad_accession(esm, accession, tmp_path, monkeypatch):
    """score_variant and embed_sequence are what BioSimEnv offers the agent. Both
    must raise, not return an error string: they return strings on other failure
    paths, so a swallowed exception would read as success."""
    monkeypatch.setattr(esm, "CACHE", tmp_path / "seqs")
    esm.attempts.clear()
    with pytest.raises(ValueError):
        esm.score_variant(accession, 1, "A")
    with pytest.raises(ValueError):
        esm.embed_sequence(accession)
    assert esm.attempts == []


def test_a_tool_call_cannot_read_a_secret_through_traversal(esm, tmp_path, monkeypatch):
    secret = tmp_path / "secret.json"
    secret.write_text(json.dumps({"sequence": "PWNED", "name": "x",
                                  "organism": "x", "length": 5}))
    cache = tmp_path / "seqs"
    cache.mkdir()
    monkeypatch.setattr(esm, "CACHE", cache)
    for call in (lambda: esm.score_variant("../secret", 1, "A"),
                 lambda: esm.embed_sequence("../secret")):
        with pytest.raises(ValueError) as refused:
            call()
        assert "PWNED" not in str(refused.value)


class _FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


@pytest.mark.parametrize("accession", ["P01308", "O73727", "A0A0B4J2D5"])
def test_a_valid_accession_is_fetched_from_the_right_url_and_cached(esm, accession, tmp_path, monkeypatch):
    """The happy path: nothing previously reached it, because the module-level stub
    always raises. Pins that the VALIDATED value is the one that reaches the URL —
    parametrized, because a single accession cannot tell a correct URL from one
    hardcoded to that same accession.
    """
    cache = tmp_path / "seqs"
    monkeypatch.setattr(esm, "CACHE", cache)
    urls: list = []

    def fake_get(url, **kwargs):
        urls.append(url)
        return _FakeResponse(
            f">sp|{accession}|EXMP_TEST Example protein OS=Testus fictus OX=9606\nMALWMRLL\n")

    monkeypatch.setattr(esm.requests, "get", fake_get)

    rec = esm.fetch_sequence(accession)

    assert urls == [f"https://rest.uniprot.org/uniprotkb/{accession}.fasta"]
    assert rec["accession"] == accession
    assert rec["organism"] == "Testus fictus"
    assert rec["sequence"] == "MALWMRLL"
    assert rec["length"] == 8

    written = cache / f"{accession}.json"
    assert written.exists(), "the fetched record must be cached"
    assert written.resolve().parent == cache.resolve()

    again = esm.fetch_sequence(accession)
    assert again == rec
    assert len(urls) == 1, "a cached accession must not be re-fetched"


def test_the_tools_report_the_validated_accession_not_the_callers_object(esm, tmp_path, monkeypatch):
    """Same residual class as the cache-path bypass: both tools interpolated the
    PARAMETER into the string handed back to the agent, so a str subclass could put
    ANSI escapes (or any text) into what the operator reads. Report rec['accession'],
    which came from the validated value."""
    cache = tmp_path / "seqs"
    cache.mkdir()
    (cache / "P01308.json").write_text(json.dumps(
        {"accession": "P01308", "name": "EXMP", "organism": "Testus fictus",
         "sequence": "MALW", "length": 4}))
    monkeypatch.setattr(esm, "CACHE", cache)
    out = esm.score_variant(_Evil("P01308"), 99, "A")
    assert "../secret" not in out, out
    assert "P01308" in out, out


def _seed_cache(esm, tmp_path, monkeypatch):
    cache = tmp_path / "seqs"
    cache.mkdir()
    (cache / "P01308.json").write_text(json.dumps(
        {"accession": "P01308", "name": "EXMP", "organism": "Testus fictus",
         "sequence": "MALW", "length": 4}))
    monkeypatch.setattr(esm, "CACHE", cache)
    return cache


def test_score_variant_reports_the_validated_accession_on_its_normal_path(esm, tmp_path, monkeypatch):
    """The success branch, reachable only with the model stubbed — the 'position
    outside' branch alone does not pin it."""
    _seed_cache(esm, tmp_path, monkeypatch)
    monkeypatch.setattr(esm, "position_logprobs",
                        lambda seq: [{"logp": {a: -1.0 for a in esm.AA}} for _ in seq])
    out = esm.score_variant(_Evil("P01308"), 2, "G")
    assert "../secret" not in out, out
    assert out.startswith("P01308 A2G"), out


def test_embed_sequence_reports_the_validated_accession(esm, tmp_path, monkeypatch):
    _seed_cache(esm, tmp_path, monkeypatch)
    monkeypatch.setattr(esm, "embed", lambda seq: [0.0] * 8)
    out = esm.embed_sequence(_Evil("P01308"))
    assert "../secret" not in out, out
    assert out.startswith("P01308 (Testus fictus, 4 aa)"), out
