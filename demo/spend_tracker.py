"""SpendTracker — the interface skeleton for /v2r-loop proving run, drain 1.

Real modules, real signatures, `NotImplementedError` bodies. This file is the one
artifact both the sealed test-author and the implementer bind to, so the symbols
they each name cannot disagree. Each stub names the build unit that fills it.

Spec: docs/demo-spec.md
"""

from __future__ import annotations

import json
import math
import os
import stat
import tempfile
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
        # A carrier, not a validator: the two numbers are recorded exactly as the
        # caller passed them and never compared, so constructing one with a total
        # at or below the ceiling is legitimate and must work.
        self.total_usd = total_usd
        self.ceiling_usd = ceiling_usd

        def as_dollars(amount: float) -> str:
            # Dollar amounts read naturally at two decimals, so an int ceiling of
            # 10 shows as $10.00 — but never round a value out of the message: a
            # sub-cent amount keeps whatever digits it actually has.
            try:
                value = float(amount)
                text = f"{value:.2f}"
                if float(text) != value:
                    text = repr(value)
            except (TypeError, ValueError):  # pragma: no cover - non-numeric carrier
                return str(amount)
            return f"${text}"

        # One argument to the base class, so str(exc) is this sentence rather than
        # an empty string or a tuple. It names both numbers: what was spent and
        # what the ceiling was.
        super().__init__(
            f"budget exceeded: total spend of {as_dollars(total_usd)} "
            f"against a ceiling of {as_dollars(ceiling_usd)}"
        )


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
        """Record one call's cost against `call_id`. — U-001

        Args:
            call_id: Identifier of the call being charged, so recorded spend stays attributable.
            cost_usd: Cost of that call in US dollars, added to this tracker's running total.
        """
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
        # A pure query: it reads the ledger through total() and changes nothing,
        # so it can be called any number of times and keeps refusing for as long
        # as the tracker is over budget.
        total = self.total()
        # The ceiling is inclusive — spending exactly the declared amount is
        # within budget. Only spend strictly above it is a refusal, otherwise a
        # run would be halted one call early.
        if total > self.ceiling_usd:
            # The real numbers, in the documented order: actual spend first, the
            # declared ceiling second.
            raise BudgetExceeded(total, self.ceiling_usd)
        return None

    def persist(self, path: str | Path) -> None:
        """Write recorded spend to `path`, durably. — U-005

        Crash-atomic: the destination is never opened for writing. The complete
        state is serialised, written to a sibling temporary file, forced to the
        disk, and only then moved into place by a single `os.replace`. A reader
        therefore sees either the whole previous state or the whole new one, and
        a failure anywhere before the replace leaves `path` exactly as it was.
        """
        destination = Path(path)

        # 1. Serialise everything FIRST, in memory. If the ledger somehow cannot
        #    be encoded, nothing has touched the disk yet.
        entries = [
            [call_id, float(cost)] for call_id, cost in self.__dict__.get("_entries", ())
        ]
        payload = json.dumps(
            {
                "version": 1,
                # The ledger is the state; the total is written alongside it so a
                # reader can cross-check, and so a hand-written state file that
                # carries only a total still restores to the right number.
                "entries": entries,
                "total_usd": self.total(),
            },
            indent=2,
            sort_keys=True,
        ).encode("utf-8") + b"\n"

        # 2. A destination whose directory does not exist yet is a first persist,
        #    not an error.
        directory = destination.parent if str(destination.parent) else Path(".")
        directory.mkdir(parents=True, exist_ok=True)

        # 3. The temporary file lives in the SAME directory, so the final replace
        #    is a rename within one filesystem — which is the atomic operation.
        fd, tmp_name = tempfile.mkstemp(
            dir=str(directory), prefix=f".{destination.name}.", suffix=".tmp"
        )
        try:
            # 4. Write the complete bytes and force them onto the disk, so the
            #    rename cannot publish a name that points at unwritten data.
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())

            # 5. mkstemp creates 0600; keep whatever mode the destination already
            #    had so persisting twice does not change its permissions.
            try:
                os.chmod(tmp_name, stat.S_IMODE(os.stat(destination).st_mode))
            except OSError:
                pass  # No previous file (or no permission to read its mode).

            # 6. The single operation that either fully happens or does not: the
            #    destination goes from the old complete state straight to the new
            #    complete state, with no truncated instant in between.
            os.replace(tmp_name, destination)
        except BaseException:
            # 7. A failed write leaves no debris behind, and leaves `path` alone.
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

        # 8. Make the rename itself durable across a power loss. Best effort:
        #    some platforms and filesystems refuse to fsync a directory.
        try:
            dir_fd = os.open(str(directory), os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(dir_fd)
        except OSError:
            pass
        finally:
            os.close(dir_fd)

    @classmethod
    def restore(cls, path: str | Path, ceiling_usd: float) -> "SpendTracker":
        """Rebuild a tracker from state previously written to `path`. — U-005

        The ceiling comes from the argument, never from the file: a resumed run
        carries the ceiling its caller declared. Every unreadable or incoherent
        detail raises rather than degrading into "nothing was spent", which is
        exactly the silent budget reset R4 exists to prevent.
        """
        source = Path(path)

        # A missing or unreadable state file raises its own OSError unchanged --
        # a resumed run must hear about it, not quietly start from zero.
        try:
            text = source.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"spend state {source!s}: not decodable as UTF-8 text") from exc

        try:
            document = json.loads(text)
        except ValueError as exc:
            # A truncated or empty file lands here. Refusing is the whole point:
            # reading it as zero spend would resume an already-spent budget.
            raise ValueError(f"spend state {source!s}: not valid JSON ({exc})") from exc

        if not isinstance(document, dict):
            raise ValueError(
                f"spend state {source!s}: expected a JSON object, "
                f"found a {type(document).__name__}"
            )

        tracker = cls(ceiling_usd)

        raw_entries = document.get("entries")
        if raw_entries is not None:
            if not isinstance(raw_entries, list):
                raise ValueError(
                    f"spend state {source!s}: 'entries' must be a list, "
                    f"found a {type(raw_entries).__name__}"
                )
            for entry in raw_entries:
                if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                    raise ValueError(
                        f"spend state {source!s}: malformed ledger entry {entry!r}"
                    )
                call_id, cost = entry
                if isinstance(cost, bool) or not isinstance(cost, (int, float)):
                    raise ValueError(
                        f"spend state {source!s}: entry {call_id!r} has a "
                        f"non-numeric cost {cost!r}"
                    )
                # Reuse the live recording path, so a restored tracker's ledger
                # is indistinguishable from one built by recording.
                tracker.record(call_id, cost)
            return tracker

        # No ledger, but a total: enough to resume honestly. Carry it as a single
        # opaque entry so further records accumulate on top of it.
        total = document.get("total_usd")
        if isinstance(total, bool) or not isinstance(total, (int, float)):
            raise ValueError(
                f"spend state {source!s}: no 'entries' list and no numeric "
                f"'total_usd' to resume from"
            )
        tracker.record("restored", total)
        return tracker

    def as_tool(self) -> "Tool":
        """Expose `record` as an aviary Tool for an Environment's tool list. — U-006"""
        # Imported here, not at module scope, so importing this module stays
        # possible where fhaviary is not installed.
        from aviary.core import Tool

        # THIS instance's bound method, so the tool an agent calls records against
        # the tracker that produced it. from_function derives the tool's name,
        # description and parameter schema from `record` itself — no wrapper
        # restates them, so the contract cannot drift from the code.
        return Tool.from_function(self.record)
