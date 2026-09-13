"""Sealed challenge suite for build unit U-002 (satisfies R2).

Contract under test (taken from the interface skeleton only -- the
implementation file was not read while writing this suite):

    def load_ceiling(path: str | Path) -> float:
        '''Read `max_spend_usd` from the YAML mapping at `path` and return it.

        Raises ConfigError if the file is missing, is not a mapping, has no
        `max_spend_usd` key, or carries a value that is not a number.
        '''

    class ConfigError(ValueError): ...

R2 says the ceiling is READ FROM CONFIGURATION; a hard-coded ceiling violates
R2 even if the unit otherwise closes. The happy-path tests therefore use
several distinct ceiling values in distinct files, so a constant return value
cannot satisfy them.

Categories
----------
functional/config-error-type    -- ConfigError is a distinct ValueError subclass
functional/config-happy-path    -- a well-formed mapping yields a float ceiling
functional/config-missing-file  -- absent path raises ConfigError
functional/config-not-mapping   -- non-mapping YAML document raises ConfigError
functional/config-key-absent    -- mapping without the key raises ConfigError
functional/config-not-number    -- non-numeric value raises ConfigError

Ambiguities recorded for the principal (deliberately NOT asserted here):
  1. A YAML boolean (`max_spend_usd: true`) is an `int` subclass in Python.
     The spec does not say whether a bool counts as "a number". Untested.
  2. Syntactically malformed YAML is not one of the four named failure modes;
     the spec does not say whether a parser error is wrapped in ConfigError or
     propagates as-is. Untested.
  3. The spec does not constrain the sign or magnitude of the ceiling, so
     negative, zero, .inf and .nan values are not asserted either way.
  4. The spec does not say whether a path naming a directory counts as
     "missing". Untested.

Only `load_ceiling` and `ConfigError` are exercised; no other stub on the
module is called or constructed.
"""

from pathlib import Path

import pytest

from demo.spend_tracker import ConfigError, load_ceiling


def _write(tmp_path: Path, name: str, text: str) -> Path:
    """Write `text` to a file under tmp_path and return its path."""
    target = tmp_path / name
    target.write_text(text, encoding="utf-8")
    return target


# ---------------------------------------------------------------------------
# functional/config-error-type
# ---------------------------------------------------------------------------


def test_config_error_is_a_proper_value_error_subclass():
    """ConfigError must be its own type, not an alias for ValueError.

    This guards every pytest.raises(ConfigError) below: if ConfigError were
    simply ValueError, those assertions could be satisfied by an incidental
    ValueError escaping from the YAML parser or from float(), rather than by a
    deliberate refusal.
    """
    assert isinstance(ConfigError, type)
    assert issubclass(ConfigError, ValueError)
    assert ConfigError is not ValueError


# ---------------------------------------------------------------------------
# functional/config-happy-path
# ---------------------------------------------------------------------------


def test_returns_declared_float_ceiling(tmp_path):
    path = _write(tmp_path, "budget.yaml", "max_spend_usd: 12.5\n")

    ceiling = load_ceiling(path)

    assert isinstance(ceiling, float)
    assert ceiling == pytest.approx(12.5)


def test_different_files_yield_their_own_ceilings(tmp_path):
    """The value must come from the file, not from a hard-coded constant (R2)."""
    cheap = _write(tmp_path, "cheap.yaml", "max_spend_usd: 0.25\n")
    rich = _write(tmp_path, "rich.yaml", "max_spend_usd: 900.75\n")

    assert load_ceiling(cheap) == pytest.approx(0.25)
    assert load_ceiling(rich) == pytest.approx(900.75)


def test_yaml_integer_is_a_number_and_comes_back_as_float(tmp_path):
    """An int is a number, and the declared return type is float."""
    path = _write(tmp_path, "int.yaml", "max_spend_usd: 25\n")

    ceiling = load_ceiling(path)

    assert isinstance(ceiling, float)
    assert ceiling == pytest.approx(25.0)


def test_accepts_the_path_as_a_plain_string(tmp_path):
    """The signature is `path: str | Path`, so a str must work too."""
    path = _write(tmp_path, "as_str.yaml", "max_spend_usd: 3.5\n")

    ceiling = load_ceiling(str(path))

    assert isinstance(ceiling, float)
    assert ceiling == pytest.approx(3.5)


def test_unrelated_keys_are_ignored(tmp_path):
    path = _write(
        tmp_path,
        "extra.yaml",
        "model: sonnet\nmax_spend_usd: 7.0\nnotes:\n  - keep going\n",
    )

    ceiling = load_ceiling(path)

    assert isinstance(ceiling, float)
    assert ceiling == pytest.approx(7.0)


# ---------------------------------------------------------------------------
# functional/config-missing-file
# ---------------------------------------------------------------------------


def test_missing_file_raises_config_error(tmp_path):
    absent = tmp_path / "nope.yaml"
    assert not absent.exists()

    with pytest.raises(ConfigError):
        load_ceiling(absent)


def test_missing_file_given_as_string_raises_config_error(tmp_path):
    absent = tmp_path / "also_nope.yaml"

    with pytest.raises(ConfigError):
        load_ceiling(str(absent))


# ---------------------------------------------------------------------------
# functional/config-not-mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name, body",
    [
        ("empty.yaml", ""),
        ("null_doc.yaml", "null\n"),
        ("sequence.yaml", "- max_spend_usd: 10.0\n"),
        ("bare_number.yaml", "10.0\n"),
        ("bare_string.yaml", "max_spend_usd\n"),
    ],
    ids=["empty", "null-document", "sequence", "bare-number", "bare-string"],
)
def test_non_mapping_document_raises_config_error(tmp_path, name, body):
    path = _write(tmp_path, name, body)

    with pytest.raises(ConfigError):
        load_ceiling(path)


# ---------------------------------------------------------------------------
# functional/config-key-absent
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name, body",
    [
        ("empty_mapping.yaml", "{}\n"),
        ("other_keys.yaml", "model: sonnet\nceiling: 10.0\n"),
        ("near_miss_key.yaml", "max_spend: 10.0\n"),
        ("nested_only.yaml", "budget:\n  max_spend_usd: 10.0\n"),
    ],
    ids=["empty-mapping", "other-keys", "near-miss-key", "nested-only"],
)
def test_absent_max_spend_usd_key_raises_config_error(tmp_path, name, body):
    path = _write(tmp_path, name, body)

    with pytest.raises(ConfigError):
        load_ceiling(path)


# ---------------------------------------------------------------------------
# functional/config-not-number
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name, body",
    [
        ("empty_value.yaml", "max_spend_usd:\n"),
        ("explicit_null.yaml", "max_spend_usd: null\n"),
        ("quoted_number.yaml", 'max_spend_usd: "12.5"\n'),
        ("word.yaml", "max_spend_usd: unlimited\n"),
        ("currency_string.yaml", 'max_spend_usd: "$12.50"\n'),
        ("sequence_value.yaml", "max_spend_usd:\n  - 10.0\n"),
        ("mapping_value.yaml", "max_spend_usd:\n  amount: 10.0\n"),
    ],
    ids=[
        "empty-value",
        "explicit-null",
        "quoted-number",
        "word",
        "currency-string",
        "sequence-value",
        "mapping-value",
    ],
)
def test_non_numeric_value_raises_config_error(tmp_path, name, body):
    path = _write(tmp_path, name, body)

    with pytest.raises(ConfigError):
        load_ceiling(path)
