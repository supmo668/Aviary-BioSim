"""SpendTracker — the interface skeleton for /v2r-loop proving run, drain 1.

Real modules, real signatures, `NotImplementedError` bodies. This file is the one
artifact both the sealed test-author and the implementer bind to, so the symbols
they each name cannot disagree. Each stub names the build unit that fills it.

Spec: docs/demo-spec.md
"""

from __future__ import annotations

from pathlib import Path


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
    raise NotImplementedError("U-003")


class SpendTracker:
    """Accumulates the cost of model calls against a declared ceiling."""

    def __init__(self, ceiling_usd: float) -> None:
        self.ceiling_usd = float(ceiling_usd)

    def record(self, call_id: str, cost_usd: float) -> None:
        """Record one call's cost against `call_id`. — U-001"""
        raise NotImplementedError("U-001")

    def total(self) -> float:
        """Return the sum of every cost recorded so far. — U-002"""
        raise NotImplementedError("U-002")

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
