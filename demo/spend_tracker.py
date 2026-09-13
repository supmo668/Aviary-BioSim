"""SpendTracker — the interface skeleton for /v2r-loop proving run, drain 1.

Real modules, real signatures, `NotImplementedError` bodies. This file is the one
artifact both the sealed test-author and the implementer bind to, so the symbols
they each name cannot disagree. Each stub names the build unit that fills it.

Spec: docs/demo-spec.md
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:  # pragma: no cover - typing only
    from aviary.core import Tool


class ConfigError(ValueError):
    """A spend configuration file could not supply a ceiling."""


class BudgetExceeded(RuntimeError):
    """Recorded spend has passed the declared ceiling.

    Carries the two numbers that make the refusal attributable. — U-005
    """

    def __init__(self, total_usd: float, ceiling_usd: float) -> None:
        raise NotImplementedError("U-005")


def load_ceiling(path: str | Path) -> float:
    """Read `max_spend_usd` from the YAML mapping at `path` and return it. — U-003

    Raises ConfigError if the file is missing, is not a mapping, has no
    `max_spend_usd` key, or carries a value that is not a number.
    """
    # Every failure below surfaces as ConfigError: this is the message a user
    # sees when their budget config is broken, so each one names the path and
    # says what was wrong with it.

    # 1. Missing, unreadable, a directory, or not decodable text.
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"spend config {path!s}: cannot read file ({exc})") from exc
    except UnicodeDecodeError as exc:
        raise ConfigError(f"spend config {path!s}: not decodable as UTF-8 text") from exc

    # 2. Parseable as YAML at all.
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"spend config {path!s}: not valid YAML ({exc})") from exc

    # 3. A mapping. An empty document parses to None, a bare scalar to a str or
    #    number, a sequence to a list — none of which can carry a key.
    if not isinstance(document, dict):
        found = "an empty document" if document is None else f"a {type(document).__name__}"
        raise ConfigError(f"spend config {path!s}: expected a YAML mapping, found {found}")

    # 4. Carries the key.
    if "max_spend_usd" not in document:
        raise ConfigError(f"spend config {path!s}: no 'max_spend_usd' key")

    # 5. Carries a number. bool is an int subclass but `true` is not a dollar
    #    amount, and a quoted "10.0" is a string that merely looks like one.
    #    NaN and the infinities are floats that cannot bound a budget.
    ceiling = document["max_spend_usd"]
    if isinstance(ceiling, bool) or not isinstance(ceiling, (int, float)):
        raise ConfigError(
            f"spend config {path!s}: 'max_spend_usd' must be a number, "
            f"found {type(ceiling).__name__} {ceiling!r}"
        )
    if not math.isfinite(ceiling):
        raise ConfigError(
            f"spend config {path!s}: 'max_spend_usd' must be a finite number, found {ceiling!r}"
        )

    return float(ceiling)


class SpendTracker:
    """Accumulates the cost of model calls against a declared ceiling."""

    def __init__(self, ceiling_usd: float) -> None:
        self.ceiling_usd = float(ceiling_usd)

    def record(self, call_id: str, cost_usd: float) -> None:
        """Record one call's cost against `call_id`. — U-001"""
        # The ledger is created on first use so it is unambiguously per-instance:
        # two trackers never share it, and __init__ stays owned by its own unit.
        if "_entries" not in self.__dict__:
            self._entries = []
        self._entries.append((str(call_id), float(cost_usd)))

    def total(self) -> float:
        """Return the sum of every cost recorded so far. — U-002"""
        # fsum, not sum: a budget guard compares this against a ceiling, so the
        # running total must be the correctly-rounded sum of the costs recorded
        # rather than an accumulation of per-addition rounding error.
        return math.fsum(cost for _, cost in self.__dict__.get("_entries", ()))

    def check(self) -> None:
        """Return None while spend is within the ceiling; refuse past it. — U-004"""
        raise NotImplementedError("U-004")

    def persist(self, path: str | Path) -> None:
        """Write recorded spend to `path`, durably. — U-006"""
        raise NotImplementedError("U-006")

    @classmethod
    def restore(cls, path: str | Path, ceiling_usd: float) -> "SpendTracker":
        """Rebuild a tracker from state previously written to `path`. — U-006"""
        raise NotImplementedError("U-006")

    def as_tool(self) -> "Tool":
        """Expose `record` as an aviary Tool for an Environment's tool list. — U-006"""
        raise NotImplementedError("U-006")
