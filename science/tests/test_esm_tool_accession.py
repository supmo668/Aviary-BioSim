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
    """The happy path: nothing previously reached it, because the `esm` fixture's
    requests.get always raises. Pins that the VALIDATED value is the one that reaches the URL —
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


# Invented for the tests below: matches the accession grammar, is asserted to denote
# nothing, and was never copied from code or data. Used where a test needs a value that
# passes validation without borrowing one that appears elsewhere in this file.
INVENTED_ACC = "Q9ZZZ9"


class _ErroringResponse(_FakeResponse):
    """A response whose status check raises — the HTTP-error path."""

    class HTTPError(Exception):     # invented; stands in for requests.HTTPError
        pass

    def raise_for_status(self):
        raise self.HTTPError("503 (invented)")


def test_an_http_error_propagates_and_writes_no_cache_file(esm, tmp_path, monkeypatch):
    """raise_for_status fires BEFORE anything is written, so a failed fetch leaves no
    record behind that a later call would trust as cached truth."""
    cache = tmp_path / "seqs"
    monkeypatch.setattr(esm, "CACHE", cache)
    urls: list = []

    def fake_get(url, **kwargs):
        urls.append(url)
        return _ErroringResponse("irrelevant")

    monkeypatch.setattr(esm.requests, "get", fake_get)
    with pytest.raises(_ErroringResponse.HTTPError):
        esm.fetch_sequence(INVENTED_ACC)
    assert list(cache.glob("*.json")) == [], "a failed fetch must not be cached"
    with pytest.raises(_ErroringResponse.HTTPError):
        esm.fetch_sequence(INVENTED_ACC)
    assert len(urls) == 2, "with nothing cached, the second call must fetch again"


def test_a_header_without_an_organism_field_records_a_question_mark(esm, tmp_path, monkeypatch):
    cache = tmp_path / "seqs"
    monkeypatch.setattr(esm, "CACHE", cache)
    monkeypatch.setattr(esm.requests, "get", lambda url, **kw: _FakeResponse(
        f">sp|{INVENTED_ACC}|EXMP_TEST Example protein\nMALW\n"))
    rec = esm.fetch_sequence(INVENTED_ACC)
    assert rec["organism"] == "?"
    assert rec["sequence"] == "MALW"


@pytest.mark.parametrize("body", ["", "   \n\n", "MALW\n"], ids=["empty", "blank", "no-header"])
def test_a_body_that_is_not_a_fasta_record_is_refused_and_not_cached(esm, body, tmp_path, monkeypatch):
    """An empty body used to raise IndexError out of lines[0] — an opaque tool error, and
    a body with no header line would have been recorded as a real sequence. Both are
    refused with a ValueError that names the accession, and nothing is written."""
    cache = tmp_path / "seqs"
    monkeypatch.setattr(esm, "CACHE", cache)
    monkeypatch.setattr(esm.requests, "get", lambda url, **kw: _FakeResponse(body))
    with pytest.raises(ValueError) as refused:
        esm.fetch_sequence(INVENTED_ACC)
    assert INVENTED_ACC in str(refused.value)
    assert list(cache.glob("*.json")) == []


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


def test_the_tools_do_not_echo_an_accession_taken_from_the_cache_file(esm, tmp_path, monkeypatch):
    """A cached record is file content, not validated input. Reporting rec["accession"]
    puts whatever the file says in front of the operator — including escape sequences."""
    cache = tmp_path / "seqs"
    cache.mkdir()
    (cache / "P01308.json").write_text(json.dumps(
        {"accession": "\x1b[2K OPERATOR-SPOOF", "name": "EXMP",
         "organism": "Testus fictus", "sequence": "MALW", "length": 4}))
    monkeypatch.setattr(esm, "CACHE", cache)
    monkeypatch.setattr(esm, "embed", lambda seq: [0.0] * 8)

    out = esm.score_variant("P01308", 99, "A")
    assert "OPERATOR-SPOOF" not in out, out
    assert "\x1b" not in out, repr(out)
    assert out.startswith("position 99 is outside P01308"), out

    out = esm.embed_sequence("P01308")
    assert "OPERATOR-SPOOF" not in out, out
    assert out.startswith("P01308 ("), out


def test_a_poisoned_cache_cannot_put_escapes_or_a_spoofed_line_in_front_of_the_operator(
        esm, tmp_path, monkeypatch):
    """The other fields of a cached record are file content too. Validating only the
    accession left organism, length and the residue raw — enough to erase the terminal
    line and print a complete, plausible result for a different entry."""
    cache = tmp_path / "seqs"
    cache.mkdir()
    (cache / "P01308.json").write_text(json.dumps({
        "accession": "P01308",
        "name": "EXMP",
        "organism": "\x1b[2K\rP99999 (Testus fictus, 110 aa) embedded: 1280-dimensional\x1b[1;32m SPOOF",
        "sequence": "M\x1b[31mLW",
        "length": "\x1b[31m9999",
    }))
    monkeypatch.setattr(esm, "CACHE", cache)
    monkeypatch.setattr(esm, "embed", lambda seq: [0.0] * 8)
    monkeypatch.setattr(esm, "position_logprobs",
                        lambda seq: [{"logp": {a: -1.0 for a in esm.AA}} for _ in seq])

    out = esm.embed_sequence("P01308")
    assert "\x1b" not in out, repr(out)
    assert "SPOOF" in out, "the text may survive; the ESCAPES must not"
    assert out.startswith("P01308 ("), out

    out = esm.score_variant("P01308", 2, "G")
    assert "\x1b" not in out, repr(out)
    assert "not a standard amino acid" in out, out

    out = esm.score_variant("P01308", 1, "G")   # position 1 IS a standard residue
    assert "\x1b" not in out, repr(out)


# --- the other two parameters ---------------------------------------------------
# The accession is validated exhaustively above. `position` and `mutant` are chosen by
# the same agent, reach the same code, and had no test at all: deleting the
# `mutant not in AA` branch outright left the whole suite green.

def _seeded(esm, tmp_path, monkeypatch, sequence="MALWMRLLPL", accession="P01308"):
    cache = tmp_path / "seqs"
    cache.mkdir()
    (cache / f"{accession}.json").write_text(json.dumps({
        "accession": accession, "name": "EXMP", "organism": "Testus fictus",
        "sequence": sequence, "length": len(sequence),
    }))
    monkeypatch.setattr(esm, "CACHE", cache)
    monkeypatch.setattr(esm, "position_logprobs",
                        lambda seq: [{"logp": {a: -1.0 for a in esm.AA}} for _ in seq])
    return esm


@pytest.mark.parametrize("mutant", [
    "",             # the empty string is a substring of every string
    "AC",           # so is any contiguous run of the alphabet
    "ACD",
    "KL",
    "ACDEFGHIKLMNPQRSTVWY",
    "a",            # lowercase is not one of the twenty
    "B",            # not an amino acid letter at all
    "\x1b[31mA",    # an escape sequence must not reach the operator
])
def test_a_mutant_that_is_not_one_single_amino_acid_is_refused(esm, tmp_path, monkeypatch,
                                                               mutant):
    """`if mutant not in AA` was substring containment, because AA is a str.

    So "", "AC" and "ACD" passed a check documented as "one of the 20 amino acids", the
    full per-residue model pass ran, and then `lp[mutant]` raised KeyError — surfaced to
    the agent by BioSimEnv.step as an opaque `tool error: KeyError: 'AC'`. The sibling
    `wt not in AA` branch added in the same change is safe only because seq[i] is always
    one character; the idiom is identical and the reasoning stated for it was not.
    """
    esm = _seeded(esm, tmp_path, monkeypatch)
    out = esm.score_variant("P01308", 2, mutant)
    assert "not one of the 20 amino acids" in out, out
    assert "\x1b" not in out, repr(out)


def test_a_valid_single_residue_substitution_still_scores(esm, tmp_path, monkeypatch):
    """The refusal above must not swallow the real path."""
    esm = _seeded(esm, tmp_path, monkeypatch)
    out = esm.score_variant("P01308", 2, "G")
    assert "not one of the 20" not in out
    assert "P01308" in out


@pytest.mark.parametrize("position", ["2", 2.0, True, None, [2]], ids=["str", "float", "bool", "none", "list"])
def test_a_position_that_is_not_a_whole_number_is_refused_not_crashed(esm, tmp_path, monkeypatch, position):
    """Values, not types, were checked: a str raised TypeError at the comparison and True
    was silently position 1. Both reach the agent as an opaque tool error or a wrong
    answer; a refusal string is what every other bad input gets."""
    esm = _seeded(esm, tmp_path, monkeypatch, accession=INVENTED_ACC)
    out = esm.score_variant(INVENTED_ACC, position, "G")
    assert "position" in out and "whole number" in out, out


@pytest.mark.parametrize("mutant", [None, ["A"], 7, b"A"], ids=["none", "list", "int", "bytes"])
def test_a_mutant_that_is_not_text_is_refused_not_crashed(esm, tmp_path, monkeypatch, mutant):
    esm = _seeded(esm, tmp_path, monkeypatch, accession=INVENTED_ACC)
    out = esm.score_variant(INVENTED_ACC, 2, mutant)
    assert "not one of the 20 amino acids" in out, out


def test_a_stored_sequence_that_is_not_text_is_refused_not_crashed(esm, tmp_path, monkeypatch):
    """A cached record is file content; its sequence field need not be a string."""
    cache = tmp_path / "seqs"
    cache.mkdir()
    (cache / f"{INVENTED_ACC}.json").write_text(json.dumps(
        {"accession": INVENTED_ACC, "name": "EXMP", "organism": "Testus fictus",
         "sequence": ["M", "A"], "length": 2}))
    monkeypatch.setattr(esm, "CACHE", cache)
    out = esm.score_variant(INVENTED_ACC, 1, "G")
    assert "stored sequence" in out and "not text" in out, out


def test_the_accession_refusal_does_not_echo_an_unbounded_input(esm):
    """The refusal echoed the full repr of whatever the agent sent, with no cap and no
    control-character stripping — the one operator-facing string operator_safe missed."""
    huge = "\x1b[2K" + "Z" * 5000
    with pytest.raises(ValueError) as refused:
        esm.valid_accession(huge)
    msg = str(refused.value)
    assert len(msg) < 300, len(msg)
    assert "\x1b" not in msg


@pytest.mark.parametrize("position", [0, -1, 11, 10**6])
def test_a_position_outside_the_sequence_is_refused(esm, tmp_path, monkeypatch, position):
    esm = _seeded(esm, tmp_path, monkeypatch)
    out = esm.score_variant("P01308", position, "G")
    assert "outside" in out, out


def test_a_long_cache_field_cannot_push_the_real_result_off_the_screen(esm, tmp_path,
                                                                       monkeypatch):
    """operator_safe strips control characters AND truncates; only the stripping was
    pinned. Both `return cleaned[:limit]` -> `return cleaned` and `limit=120` -> `10**9`
    survived the whole suite. A cached organism field of 100 KB of ordinary printable
    text floods the terminal and scrolls the real answer away — the same threat as an
    escape sequence, one mechanism over."""
    flood = "A" * 100_000
    cache = tmp_path / "seqs"
    cache.mkdir()
    (cache / "P01308.json").write_text(json.dumps({
        "accession": "P01308", "name": "EXMP", "organism": flood,
        "sequence": "MALW", "length": flood,
    }))
    monkeypatch.setattr(esm, "CACHE", cache)
    monkeypatch.setattr(esm, "embed", lambda seq: [0.0] * 8)

    out = esm.embed_sequence("P01308")
    assert len(out) < 400, f"a cache field flooded the operator with {len(out)} chars"
    assert "embedded" in out, "the tool's own result must survive the truncation"


def test_operator_safe_truncates_at_its_stated_limit(esm):
    assert len(esm.operator_safe("x" * 500)) == 120
    assert len(esm.operator_safe("x" * 119)) == 119
    assert len(esm.operator_safe("x" * 120)) == 120


def test_the_stub_tool_has_the_same_signature_as_the_real_one(esm, esm_stub):
    """BioSimEnv.reset builds the agent's tool schema with Tool.from_function on whatever
    sys.modules holds. In tests that is the stub, so ~12 budget tests exercise a schema
    that cannot exist in production: the stub took (accession, mutation) while the real
    tool takes (accession, position, mutant). Renaming or adding a required parameter on
    the real tool left all of them green."""
    import inspect
    real = inspect.signature(esm.score_variant)
    stub = inspect.signature(esm_stub.score_variant)
    assert list(stub.parameters) == list(real.parameters), (
        f"stub {list(stub.parameters)} vs real {list(real.parameters)} — the budget tests "
        "would be measuring a tool shape production never sees")
