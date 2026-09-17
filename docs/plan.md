# /v2r-loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `/v2r-loop` — a skill that takes one vision string and drives it to a reviewed branch of working, individually-tested code, with a register CLI that owns every state transition.

**Architecture:** Two artifacts. `scripts/register.py` is a PEP 723 single-file CLI with no LLM in it; it owns the register, re-runs sealed tests itself, and refuses any transition it cannot independently verify. `SKILL.md` is the driver: it sequences the stages, invokes `/research`, `/grill-with-docs` and `/writing-plans` during alignment, and dispatches subagents during the drain — but it can never assert a close.

**Tech Stack:** Python 3.14 via `uv run` (PEP 723 inline deps), PyYAML, pytest, git plumbing via `subprocess`, `weave` for trace spans (optional import), W&B Inference (`deepseek-ai/DeepSeek-V4-Pro-0813`) for any direct model call.

## Global Constraints

- **Work in the worktree** `/Users/mo/github/personal/Aviary-BioSim` (branch
  `v2r-loop`). Never `cd` to the main checkout; never touch `main`.
- **Raw `git commit` is hook-blocked** by aiadlc's `block-raw-tools.sh`. Every commit goes
  through the sanctioned wrapper. Export this once per shell before committing:
  ```bash
  export AIADLC=/Users/mo/.claude/plugins/cache/aiadlc-plugins/aiadlc/0.54.0
  ```
  then `git add <paths>` followed by
  `"$AIADLC/tools/git-safe-commit" "<summary>" --no-work-item --staged`.

- Spec: `docs/spec.md`. Glossary: `docs/CONTEXT.md`. Decisions: `docs/adr/0001`–`0004`.
- **`register.py` contains no LLM call and no network call.** Its correctness is what the rest of the system trusts.
- **The model may never assert a close.** Every `close` re-runs the sealed test in-process and refuses unless it observes a pass.
- **Never write `main`.** `agency.yaml` sets `cto.branch: main` and `protected_branches` defaults to it. The loop runs in a worktree where `branch == agent name` and hands a PR to the CTO.
- Vocabulary is fixed by the glossary: **vision, alignment, requirement (`R<n>`), build unit (`U-nnn`), register, sealed test, close, park, drain, run record, instinct pin, halt.** Do not introduce `task`, `slice`, `obligation`, `blocked_by`, or `rung`.
- **No dependency graph.** A park is local (ADR-0004). Do not add `blocked_by` or cascade logic.
- Run state lives under `.v2r/` at repo root and **must be gitignored**. This is load-bearing,
  not hygiene: `park` runs `git add -A` followed by `git reset --hard <pre_claim_sha>`, and an
  un-ignored `.v2r/` would be committed into the attempt branch and then *deleted* by the
  reset, destroying the register and the evidence mid-park. Sealed tests live under
  `tests/sealed/v2r/` and are tracked normally.
- All commands are run with `uv run`; system Python has no pytest.

---

## File Structure

| File | Responsibility |
|---|---|
| `.claude/skills/v2r-loop/SKILL.md` | The driver. Stages 0–4, one `vision` parameter, subagent dispatch, skill invocation. No state mutation. |
| `.claude/skills/v2r-loop/scripts/register.py` | Every state transition. Schema, git plumbing, sealed-test execution, ceilings, run record, weave spans. |
| `.claude/skills/v2r-loop/scripts/tests/test_register_state.py` | Schema round-trip, `next`, `claim`. |
| `.claude/skills/v2r-loop/scripts/tests/test_register_close.py` | `close` refusal matrix — the adversarial core. |
| `.claude/skills/v2r-loop/scripts/tests/test_register_park.py` | Tree-revert and branch-preservation invariants. |
| `.claude/skills/v2r-loop/scripts/tests/test_register_ceilings.py` | Halt vs park separation. |
| `.claude/skills/v2r-loop/scripts/tests/test_register_record.py` | Run record, instinct pin, replay determinism. |
| `.claude/skills/v2r-loop/scripts/tests/conftest.py` | `git_repo` fixture — a real throwaway repo per test. |

`register.py` is one file on purpose: it is the trusted component, and it should be readable in a single sitting.

---

### Task 1: Register schema and read-only commands

**Files:**
- Create: `.claude/skills/v2r-loop/scripts/register.py`
- Create: `.claude/skills/v2r-loop/scripts/tests/conftest.py`
- Test: `.claude/skills/v2r-loop/scripts/tests/test_register_state.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `load(path: Path) -> dict`, `save(path: Path, data: dict) -> None`, `cmd_status(args) -> int`, `cmd_next(args) -> int`, module constant `V2R_DIR = Path(".v2r")`, `REGISTER = V2R_DIR / "register.yaml"`. Unit states are the exact strings `"open"`, `"claimed"`, `"closed"`, `"parked"`.

- [ ] **Step 1: Gitignore the run directory**

```bash
cd /Users/mo/github/personal/Aviary-BioSim
printf '\n# /v2r-loop run state — must stay untracked (see plan Global Constraints)\n.v2r/\n' >> .gitignore
git check-ignore -q .v2r/register.yaml && echo "ignored OK"
```

Expected: `ignored OK`

- [ ] **Step 2: Write the conftest fixture**

Create `.claude/skills/v2r-loop/scripts/tests/conftest.py`:

```python
import subprocess
from pathlib import Path

import pytest


def git(*args, cwd):
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def git_repo(tmp_path, monkeypatch):
    """A real git repo with one commit, cwd set to it."""
    git("init", "-q", "-b", "main", cwd=tmp_path)
    git("config", "user.email", "test@example.com", cwd=tmp_path)
    git("config", "user.name", "Test", cwd=tmp_path)
    (tmp_path / "README.md").write_text("seed\n")
    git("add", "README.md", cwd=tmp_path)
    git("commit", "-q", "-m", "seed", cwd=tmp_path)
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def register_data():
    return {
        "version": 1,
        "run": {
            "drain": 1,
            "seed": 1337,
            "instinct_pin": None,
            "ceilings": {
                "max_drains": 3,
                "max_attempts": 3,
                "max_wall_clock_s": 21600,
                "max_spend_usd": 25,
            },
        },
        "units": [
            {
                "id": "U-001",
                "satisfies": "R1",
                "statement": "SpendTracker.record accumulates per-call cost",
                "stub": "skeleton/spend_tracker.py::SpendTracker.record",
                "sealed_test": "tests/sealed/v2r/test_u001.py",
                "sealed_test_sha": None,
                "state": "open",
                "attempts": 0,
                "pre_claim_sha": None,
                "evidence": None,
                "park_branch": None,
            },
            {
                "id": "U-002",
                "satisfies": "R1",
                "statement": "SpendTracker.total sums recorded costs",
                "stub": "skeleton/spend_tracker.py::SpendTracker.total",
                "sealed_test": "tests/sealed/v2r/test_u002.py",
                "sealed_test_sha": None,
                "state": "closed",
                "attempts": 1,
                "pre_claim_sha": None,
                "evidence": None,
                "park_branch": None,
            },
        ],
    }
```

- [ ] **Step 3: Write the failing test**

Create `.claude/skills/v2r-loop/scripts/tests/test_register_state.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import register  # noqa: E402


def test_round_trip_preserves_units(git_repo, register_data):
    register.V2R_DIR.mkdir()
    register.save(register.REGISTER, register_data)
    loaded = register.load(register.REGISTER)
    assert loaded == register_data


def test_next_returns_first_open_unit(git_repo, register_data):
    register.V2R_DIR.mkdir()
    register.save(register.REGISTER, register_data)
    assert register.next_open(register_data) == "U-001"


def test_next_returns_none_when_nothing_open(git_repo, register_data):
    for unit in register_data["units"]:
        unit["state"] = "closed"
    assert register.next_open(register_data) is None


def test_next_skips_parked_units(git_repo, register_data):
    register_data["units"][0]["state"] = "parked"
    assert register.next_open(register_data) is None
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `cd /Users/mo/github/personal/Aviary-BioSim/.claude/skills/v2r-loop/scripts && uv run --with pytest --with pyyaml pytest tests/test_register_state.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'register'`

- [ ] **Step 5: Write the minimal implementation**

Create `.claude/skills/v2r-loop/scripts/register.py`:

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml"]
# ///
"""Register CLI for /v2r-loop.

Owns every state transition. Contains no LLM call and no network call: the rest of
the system trusts this file's correctness, so it must be verifiable by reading it.

See docs/adr/0001-register-cli-owns-every-transition.md
"""

import argparse
import sys
from pathlib import Path

import yaml

V2R_DIR = Path(".v2r")
REGISTER = V2R_DIR / "register.yaml"

OPEN, CLAIMED, CLOSED, PARKED = "open", "claimed", "closed", "parked"


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def unit_by_id(data: dict, unit_id: str) -> dict:
    for unit in data["units"]:
        if unit["id"] == unit_id:
            return unit
    raise KeyError(f"no such build unit: {unit_id}")


def next_open(data: dict) -> str | None:
    for unit in data["units"]:
        if unit["state"] == OPEN:
            return unit["id"]
    return None


def cmd_status(args) -> int:
    data = load(REGISTER)
    counts: dict[str, int] = {}
    for unit in data["units"]:
        counts[unit["state"]] = counts.get(unit["state"], 0) + 1
    print(f"drain {data['run']['drain']}  pin {data['run']['instinct_pin']}")
    for state in (OPEN, CLAIMED, CLOSED, PARKED):
        print(f"  {state:8} {counts.get(state, 0)}")
    return 0


def cmd_next(args) -> int:
    unit_id = next_open(load(REGISTER))
    if unit_id is None:
        return 1
    print(unit_id)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="register")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="summarise register state").set_defaults(fn=cmd_status)
    sub.add_parser("next", help="print the next open build unit id").set_defaults(fn=cmd_next)
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd /Users/mo/github/personal/Aviary-BioSim/.claude/skills/v2r-loop/scripts && uv run --with pytest --with pyyaml pytest tests/test_register_state.py -v`

Expected: PASS, 4 passed

- [ ] **Step 7: Commit**

```bash
cd /Users/mo/github/personal/Aviary-BioSim
git add .gitignore .claude/skills/v2r-loop/scripts/register.py .claude/skills/v2r-loop/scripts/tests/
"$AIADLC/tools/git-safe-commit" "feat(v2r-loop): register schema and read-only commands" --no-work-item --staged
```

---

### Task 2: `claim` records the pre-claim tree

**Files:**
- Modify: `.claude/skills/v2r-loop/scripts/register.py`
- Test: `.claude/skills/v2r-loop/scripts/tests/test_register_state.py`

**Interfaces:**
- Consumes: `load`, `save`, `unit_by_id`, `next_open` from Task 1.
- Produces: `git(*args) -> str` (runs git in cwd, returns stripped stdout, raises `subprocess.CalledProcessError` on failure), `head_sha() -> str`, `cmd_claim(args) -> int`. After `claim`, the unit has `state == "claimed"` and `pre_claim_sha` set to the commit SHA the tree stood at. `park` in Task 5 resets to exactly this value.

- [ ] **Step 1: Write the failing test**

Append to `.claude/skills/v2r-loop/scripts/tests/test_register_state.py`:

```python
def test_claim_marks_unit_and_records_pre_claim_sha(git_repo, register_data):
    register.V2R_DIR.mkdir()
    register.save(register.REGISTER, register_data)

    assert register.main(["claim", "U-001"]) == 0

    unit = register.unit_by_id(register.load(register.REGISTER), "U-001")
    assert unit["state"] == "claimed"
    assert unit["pre_claim_sha"] == register.head_sha()


def test_claim_refuses_a_unit_that_is_not_open(git_repo, register_data):
    register.V2R_DIR.mkdir()
    register.save(register.REGISTER, register_data)

    assert register.main(["claim", "U-002"]) == 2

    unit = register.unit_by_id(register.load(register.REGISTER), "U-002")
    assert unit["state"] == "closed"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /Users/mo/github/personal/Aviary-BioSim/.claude/skills/v2r-loop/scripts && uv run --with pytest --with pyyaml pytest tests/test_register_state.py -v`

Expected: FAIL with `AttributeError: module 'register' has no attribute 'head_sha'`

- [ ] **Step 3: Write the minimal implementation**

In `register.py`, add `subprocess` to the imports, then add these functions above `cmd_status`:

```python
def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def head_sha() -> str:
    return git("rev-parse", "HEAD")


def cmd_claim(args) -> int:
    data = load(REGISTER)
    unit = unit_by_id(data, args.unit)
    if unit["state"] != OPEN:
        print(f"{unit['id']} is {unit['state']}, not open", file=sys.stderr)
        return 2
    unit["state"] = CLAIMED
    unit["pre_claim_sha"] = head_sha()
    save(REGISTER, data)
    print(f"claimed {unit['id']} at {unit['pre_claim_sha'][:8]}")
    return 0
```

Register the subcommand in `build_parser`, immediately after the `next` parser:

```python
    claim = sub.add_parser("claim", help="claim the next build unit")
    claim.add_argument("unit")
    claim.set_defaults(fn=cmd_claim)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /Users/mo/github/personal/Aviary-BioSim/.claude/skills/v2r-loop/scripts && uv run --with pytest --with pyyaml pytest tests/test_register_state.py -v`

Expected: PASS, 6 passed

- [ ] **Step 5: Commit**

```bash
cd /Users/mo/github/personal/Aviary-BioSim
git add .claude/skills/v2r-loop/scripts/
"$AIADLC/tools/git-safe-commit" "feat(v2r-loop): claim records the pre-claim tree SHA" --no-work-item --staged
```

---

### Task 3: `close` re-runs the sealed test and refuses on failure

This is the task the entire design rests on. `close` must be impossible to talk into succeeding.

**Files:**
- Modify: `.claude/skills/v2r-loop/scripts/register.py`
- Test: `.claude/skills/v2r-loop/scripts/tests/test_register_close.py`

**Interfaces:**
- Consumes: `git`, `head_sha`, `load`, `save`, `unit_by_id` from Tasks 1–2.
- Produces: `run_sealed_test(path: str) -> tuple[int, str]` returning `(exit_code, combined_output)`, module constant `EXIT_NO_SEALED_TEST = 90`, and `cmd_close(args) -> int` with exit codes `0` closed, `1` test failed (attempt recorded, unit stays claimed), `3` **halt** — the gate could not execute.

**The pytest exit-code mapping is the rule, and it is exact:**

| pytest exit | Meaning | `close` response |
|---|---|---|
| 0 | all passed | close the unit, commit |
| 1 | tests failed | increment `attempts`, return 1 |
| 2, 3, 4, 5 | interrupted / internal error / usage error / **no tests collected** | **halt**, return 3 |
| 90 | sealed test file absent (ours, not pytest's) | **halt**, return 3 |

Exit 5 matters most: an empty or uncollectable sealed test would otherwise "pass" by never failing. A gate that cannot execute is a broken gate, not a failed unit.

- [ ] **Step 1: Write the failing test**

Create `.claude/skills/v2r-loop/scripts/tests/test_register_close.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import register  # noqa: E402


def _seed(git_repo, register_data, test_body: str) -> Path:
    register.V2R_DIR.mkdir()
    sealed = git_repo / "tests" / "sealed" / "v2r"
    sealed.mkdir(parents=True)
    test_file = sealed / "test_u001.py"
    test_file.write_text(test_body)
    register_data["units"][0]["state"] = "claimed"
    register_data["units"][0]["pre_claim_sha"] = register.head_sha()
    register.save(register.REGISTER, register_data)
    return test_file


def test_close_succeeds_and_commits_when_the_sealed_test_passes(git_repo, register_data):
    _seed(git_repo, register_data, "def test_ok():\n    assert True\n")

    assert register.main(["close", "U-001"]) == 0

    unit = register.unit_by_id(register.load(register.REGISTER), "U-001")
    assert unit["state"] == "closed"
    assert "U-001" in register.git("log", "-1", "--pretty=%s")


def test_close_refuses_when_the_sealed_test_fails(git_repo, register_data):
    _seed(git_repo, register_data, "def test_no():\n    assert False\n")

    assert register.main(["close", "U-001"]) == 1

    unit = register.unit_by_id(register.load(register.REGISTER), "U-001")
    assert unit["state"] == "claimed"
    assert unit["attempts"] == 1


def test_close_halts_when_the_sealed_test_collects_nothing(git_repo, register_data):
    _seed(git_repo, register_data, "# no tests here\n")

    assert register.main(["close", "U-001"]) == 3

    unit = register.unit_by_id(register.load(register.REGISTER), "U-001")
    assert unit["state"] == "claimed"


def test_close_halts_when_the_sealed_test_is_missing(git_repo, register_data):
    register.V2R_DIR.mkdir()
    register_data["units"][0]["state"] = "claimed"
    register.save(register.REGISTER, register_data)

    assert register.main(["close", "U-001"]) == 3


def test_close_halts_when_the_sealed_test_has_a_syntax_error(git_repo, register_data):
    _seed(git_repo, register_data, "def test_broken(:\n")

    assert register.main(["close", "U-001"]) == 3
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /Users/mo/github/personal/Aviary-BioSim/.claude/skills/v2r-loop/scripts && uv run --with pytest --with pyyaml pytest tests/test_register_close.py -v`

Expected: FAIL — `argument command: invalid choice: 'close'`

- [ ] **Step 3: Write the minimal implementation**

In `register.py`, add these above `build_parser`:

```python
PYTEST_PASSED = 0
PYTEST_FAILED = 1
EXIT_NO_SEALED_TEST = 90  # ours, deliberately outside pytest's 0-5 exit space
EXIT_CLOSED, EXIT_TEST_FAILED, EXIT_HALT = 0, 1, 3


def run_sealed_test(path: str) -> tuple[int, str]:
    """Run one sealed test. Returns (pytest exit code, combined output).

    Exit 5 (no tests collected) is NOT a pass: a sealed test that collects
    nothing would otherwise close a unit by never failing.
    """
    if not Path(path).exists():
        return EXIT_NO_SEALED_TEST, f"sealed test not found: {path}"
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", path, "-q", "--no-header", "-p", "no:cacheprovider"],
        capture_output=True,
        text=True,
    )
    return completed.returncode, completed.stdout + completed.stderr


def cmd_close(args) -> int:
    data = load(REGISTER)
    unit = unit_by_id(data, args.unit)

    code, output = run_sealed_test(unit["sealed_test"])

    if code not in (PYTEST_PASSED, PYTEST_FAILED):
        print(f"HALT: gate could not execute for {unit['id']} (pytest exit {code})", file=sys.stderr)
        print(output, file=sys.stderr)
        return EXIT_HALT

    if code == PYTEST_FAILED:
        unit["attempts"] += 1
        save(REGISTER, data)
        print(f"{unit['id']} failed its sealed test (attempt {unit['attempts']})", file=sys.stderr)
        return EXIT_TEST_FAILED

    unit["state"] = CLOSED
    save(REGISTER, data)
    git("add", "-A")
    git("commit", "-q", "-m", f"{unit['id']} {unit['statement']} (satisfies {unit['satisfies']})")
    print(f"closed {unit['id']}")
    return EXIT_CLOSED
```

Register the subcommand in `build_parser`:

```python
    close = sub.add_parser("close", help="close a unit if its sealed test passes")
    close.add_argument("unit")
    close.set_defaults(fn=cmd_close)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /Users/mo/github/personal/Aviary-BioSim/.claude/skills/v2r-loop/scripts && uv run --with pytest --with pyyaml pytest tests/test_register_close.py -v`

Expected: PASS, 5 passed

- [ ] **Step 5: Commit**

```bash
cd /Users/mo/github/personal/Aviary-BioSim
git add .claude/skills/v2r-loop/scripts/
"$AIADLC/tools/git-safe-commit" "feat(v2r-loop): close re-runs the sealed test and halts when the gate cannot execute" --no-work-item --staged
```

---

### Task 4: `close` refuses a sealed test that changed after authoring

The implementer never sees the sealed test, but nothing yet stops it from *editing* one. The `test-seal` PreToolUse hook blocks the obvious path; this closes the rest.

**Files:**
- Modify: `.claude/skills/v2r-loop/scripts/register.py`
- Test: `.claude/skills/v2r-loop/scripts/tests/test_register_close.py`

**Interfaces:**
- Consumes: `run_sealed_test`, `cmd_close` from Task 3.
- Produces: `sha256_file(path: str) -> str` returning a bare lowercase hex digest, and `cmd_seal(args) -> int` which records `sealed_test_sha` after the test-author writes the test. `cmd_close` gains a pre-flight integrity check returning `EXIT_HALT` on mismatch.

- [ ] **Step 1: Write the failing test**

Append to `.claude/skills/v2r-loop/scripts/tests/test_register_close.py`:

```python
def test_seal_records_the_sealed_test_digest(git_repo, register_data):
    test_file = _seed(git_repo, register_data, "def test_ok():\n    assert True\n")

    assert register.main(["seal", "U-001"]) == 0

    unit = register.unit_by_id(register.load(register.REGISTER), "U-001")
    assert unit["sealed_test_sha"] == register.sha256_file(str(test_file))


def test_close_halts_when_the_sealed_test_was_modified_after_sealing(git_repo, register_data):
    test_file = _seed(git_repo, register_data, "def test_ok():\n    assert 1 == 2\n")
    register.main(["seal", "U-001"])

    test_file.write_text("def test_ok():\n    assert True\n")

    assert register.main(["close", "U-001"]) == 3

    unit = register.unit_by_id(register.load(register.REGISTER), "U-001")
    assert unit["state"] == "claimed"


def test_close_still_works_when_the_test_is_unmodified(git_repo, register_data):
    _seed(git_repo, register_data, "def test_ok():\n    assert True\n")
    register.main(["seal", "U-001"])

    assert register.main(["close", "U-001"]) == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /Users/mo/github/personal/Aviary-BioSim/.claude/skills/v2r-loop/scripts && uv run --with pytest --with pyyaml pytest tests/test_register_close.py -v`

Expected: FAIL — `argument command: invalid choice: 'seal'`

- [ ] **Step 3: Write the minimal implementation**

In `register.py`, add `import hashlib` to the imports and these functions above `cmd_close`:

```python
def sha256_file(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cmd_seal(args) -> int:
    """Record the sealed test's digest. Run once, after the test-author writes it."""
    data = load(REGISTER)
    unit = unit_by_id(data, args.unit)
    if not Path(unit["sealed_test"]).exists():
        print(f"sealed test not found: {unit['sealed_test']}", file=sys.stderr)
        return 2
    unit["sealed_test_sha"] = sha256_file(unit["sealed_test"])
    save(REGISTER, data)
    print(f"sealed {unit['id']} {unit['sealed_test_sha'][:12]}")
    return 0
```

In `cmd_close`, insert this integrity check immediately after `unit = unit_by_id(data, args.unit)`:

```python
    recorded = unit.get("sealed_test_sha")
    if recorded and Path(unit["sealed_test"]).exists():
        actual = sha256_file(unit["sealed_test"])
        if actual != recorded:
            print(
                f"HALT: sealed test for {unit['id']} changed after sealing "
                f"({recorded[:12]} -> {actual[:12]})",
                file=sys.stderr,
            )
            return EXIT_HALT
```

Register the subcommand in `build_parser`:

```python
    seal = sub.add_parser("seal", help="record the sealed test digest after authoring")
    seal.add_argument("unit")
    seal.set_defaults(fn=cmd_seal)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /Users/mo/github/personal/Aviary-BioSim/.claude/skills/v2r-loop/scripts && uv run --with pytest --with pyyaml pytest tests/test_register_close.py -v`

Expected: PASS, 8 passed

- [ ] **Step 5: Commit**

```bash
cd /Users/mo/github/personal/Aviary-BioSim
git add .claude/skills/v2r-loop/scripts/
"$AIADLC/tools/git-safe-commit" "feat(v2r-loop): close halts when a sealed test changed after sealing" --no-work-item --staged
```

---

### Task 5: `park` reverts the tree and preserves the attempt

**Files:**
- Modify: `.claude/skills/v2r-loop/scripts/register.py`
- Test: `.claude/skills/v2r-loop/scripts/tests/test_register_park.py`

**Interfaces:**
- Consumes: `git`, `load`, `save`, `unit_by_id`, `head_sha` from Tasks 1–2.
- Produces: `cmd_park(args) -> int`. On park: the attempt is committed to branch `park/<unit-id>`, the working tree is `git reset --hard <pre_claim_sha>`, `evidence` points at `.v2r/parked/<unit-id>.out`, `park_branch` is set, `state` becomes `"parked"`.

Per ADR-0004 a park is **local** — it sets no `blocked_by` and touches no other unit. Do not add cascade logic.

- [ ] **Step 1: Write the failing test**

Create `.claude/skills/v2r-loop/scripts/tests/test_register_park.py`:

```python
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import register  # noqa: E402


def _claimed_with_attempt(git_repo, register_data) -> str:
    register.V2R_DIR.mkdir()
    register_data["units"][0]["state"] = "claimed"
    register_data["units"][0]["pre_claim_sha"] = register.head_sha()
    register_data["units"][0]["attempts"] = 3
    register.save(register.REGISTER, register_data)
    clean_tree = register.git("rev-parse", "HEAD^{tree}")
    (git_repo / "half_built.py").write_text("def record(:  # broken\n")
    return clean_tree


def test_park_restores_the_tree_exactly(git_repo, register_data):
    clean_tree = _claimed_with_attempt(git_repo, register_data)
    (git_repo / ".v2r" / "evidence.out").write_text("pytest said no\n")

    assert register.main(["park", "U-001", "--evidence", ".v2r/evidence.out"]) == 0

    assert register.git("rev-parse", "HEAD^{tree}") == clean_tree
    assert not (git_repo / "half_built.py").exists()


def test_park_preserves_the_attempt_on_a_branch(git_repo, register_data):
    _claimed_with_attempt(git_repo, register_data)
    (git_repo / ".v2r" / "evidence.out").write_text("pytest said no\n")

    register.main(["park", "U-001", "--evidence", ".v2r/evidence.out"])

    branches = register.git("branch", "--list", "park/U-001")
    assert "park/U-001" in branches
    contents = register.git("show", "park/U-001:half_built.py")
    assert "broken" in contents


def test_park_marks_the_unit_and_keeps_the_evidence(git_repo, register_data):
    _claimed_with_attempt(git_repo, register_data)
    (git_repo / ".v2r" / "evidence.out").write_text("pytest said no\n")

    register.main(["park", "U-001", "--evidence", ".v2r/evidence.out"])

    unit = register.unit_by_id(register.load(register.REGISTER), "U-001")
    assert unit["state"] == "parked"
    assert unit["park_branch"] == "park/U-001"
    assert Path(unit["evidence"]).read_text() == "pytest said no\n"


def test_park_does_not_touch_any_other_unit(git_repo, register_data):
    _claimed_with_attempt(git_repo, register_data)
    (git_repo / ".v2r" / "evidence.out").write_text("nope\n")

    register.main(["park", "U-001", "--evidence", ".v2r/evidence.out"])

    other = register.unit_by_id(register.load(register.REGISTER), "U-002")
    assert other["state"] == "closed"
    assert "blocked_by" not in other
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /Users/mo/github/personal/Aviary-BioSim/.claude/skills/v2r-loop/scripts && uv run --with pytest --with pyyaml pytest tests/test_register_park.py -v`

Expected: FAIL — `argument command: invalid choice: 'park'`

- [ ] **Step 3: Write the minimal implementation**

In `register.py`, add above `build_parser`:

Add `import shutil` to the imports at the top of the file, then add this above `build_parser`:

```python
def cmd_park(args) -> int:
    """Retire one build unit. Preserve the attempt, restore the tree, record why.

    A park is local: it says nothing about any other unit. See ADR-0004.
    """
    data = load(REGISTER)
    unit = unit_by_id(data, args.unit)
    pre_claim = unit["pre_claim_sha"]
    if not pre_claim:
        print(f"{unit['id']} has no pre_claim_sha; was it claimed?", file=sys.stderr)
        return 2

    branch = f"park/{unit['id']}"
    parked_dir = V2R_DIR / "parked"
    parked_dir.mkdir(parents=True, exist_ok=True)
    evidence_dest = parked_dir / f"{unit['id']}.out"
    shutil.copyfile(args.evidence, evidence_dest)

    # Preserve the attempt on its own branch, then restore the tree.
    git("add", "-A")
    git("commit", "-q", "--allow-empty", "-m", f"parked attempt for {unit['id']}")
    git("branch", "-f", branch, "HEAD")
    git("reset", "-q", "--hard", pre_claim)

    unit["state"] = PARKED
    unit["park_branch"] = branch
    unit["evidence"] = str(evidence_dest)
    save(REGISTER, data)
    print(f"parked {unit['id']} -> {branch}; tree restored to {pre_claim[:8]}")
    return 0
```

Register the subcommand in `build_parser`:

```python
    park = sub.add_parser("park", help="retire a unit, preserving the attempt")
    park.add_argument("unit")
    park.add_argument("--evidence", required=True, help="path to the failing test output")
    park.set_defaults(fn=cmd_park)
```

**Why the ordering is safe:** `.v2r/` is gitignored (Task 1, Step 1), so `git add -A` never
stages the register or the evidence, and `git reset --hard` never deletes them. The attempt
branch contains only the implementer's code. If any of the four tests fail on a missing
`.v2r/` path, the gitignore step was skipped — fix that rather than reordering this function.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /Users/mo/github/personal/Aviary-BioSim/.claude/skills/v2r-loop/scripts && uv run --with pytest --with pyyaml pytest tests/test_register_park.py -v`

Expected: PASS, 4 passed

- [ ] **Step 5: Commit**

```bash
cd /Users/mo/github/personal/Aviary-BioSim
git add .claude/skills/v2r-loop/scripts/
"$AIADLC/tools/git-safe-commit" "feat(v2r-loop): park reverts the tree and preserves the attempt on a branch" --no-work-item --staged
```

---

### Task 6: Ceilings halt the drain, and a halt is not a park

**Files:**
- Modify: `.claude/skills/v2r-loop/scripts/register.py`
- Test: `.claude/skills/v2r-loop/scripts/tests/test_register_ceilings.py`

**Interfaces:**
- Consumes: `load`, `save`, `unit_by_id` from Task 1.
- Produces: `check_ceilings(data: dict, started_at: float, spend_usd: float) -> str | None` returning a human-readable breach reason or `None`, and `cmd_check(args) -> int` returning `0` when within ceilings and `3` on breach. `attempts_exhausted(unit, data) -> bool` is the separate predicate the driver uses to decide *park*.

The distinction is the point: **attempts exhausted → park one unit, drain continues. Ceiling breached → halt the whole drain, every unit left as it stands.**

- [ ] **Step 1: Write the failing test**

Create `.claude/skills/v2r-loop/scripts/tests/test_register_ceilings.py`:

```python
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import register  # noqa: E402


def test_within_ceilings_returns_none(register_data):
    assert register.check_ceilings(register_data, started_at=time.time(), spend_usd=0.0) is None


def test_wall_clock_breach_is_reported(register_data):
    started = time.time() - 99_999
    reason = register.check_ceilings(register_data, started_at=started, spend_usd=0.0)
    assert reason is not None
    assert "wall clock" in reason


def test_spend_breach_is_reported(register_data):
    reason = register.check_ceilings(register_data, started_at=time.time(), spend_usd=999.0)
    assert reason is not None
    assert "spend" in reason


def test_drain_cap_breach_is_reported(register_data):
    register_data["run"]["drain"] = 4
    reason = register.check_ceilings(register_data, started_at=time.time(), spend_usd=0.0)
    assert reason is not None
    assert "drain" in reason


def test_attempts_exhausted_is_a_separate_predicate(register_data):
    unit = register_data["units"][0]
    unit["attempts"] = 3
    assert register.attempts_exhausted(unit, register_data) is True
    unit["attempts"] = 2
    assert register.attempts_exhausted(unit, register_data) is False


def test_exhausted_attempts_do_not_breach_a_ceiling(register_data):
    register_data["units"][0]["attempts"] = 99
    assert register.check_ceilings(register_data, started_at=time.time(), spend_usd=0.0) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /Users/mo/github/personal/Aviary-BioSim/.claude/skills/v2r-loop/scripts && uv run --with pytest --with pyyaml pytest tests/test_register_ceilings.py -v`

Expected: FAIL with `AttributeError: module 'register' has no attribute 'check_ceilings'`

- [ ] **Step 3: Write the minimal implementation**

In `register.py`, add `import time` to the imports and these functions above `build_parser`:

```python
def attempts_exhausted(unit: dict, data: dict) -> bool:
    """Per-unit budget. Exhausting it parks ONE unit; the drain continues."""
    return unit["attempts"] >= data["run"]["ceilings"]["max_attempts"]


def check_ceilings(data: dict, started_at: float, spend_usd: float) -> str | None:
    """Whole-drain budget. A breach halts the drain; it never parks a unit."""
    ceilings = data["run"]["ceilings"]
    if data["run"]["drain"] > ceilings["max_drains"]:
        return f"drain cap: {data['run']['drain']} > {ceilings['max_drains']}"
    elapsed = time.time() - started_at
    if elapsed > ceilings["max_wall_clock_s"]:
        return f"wall clock: {elapsed:.0f}s > {ceilings['max_wall_clock_s']}s"
    if spend_usd > ceilings["max_spend_usd"]:
        return f"spend: ${spend_usd:.2f} > ${ceilings['max_spend_usd']}"
    return None


def cmd_check(args) -> int:
    data = load(REGISTER)
    reason = check_ceilings(data, started_at=args.started_at, spend_usd=args.spend_usd)
    if reason:
        print(f"HALT: {reason}", file=sys.stderr)
        return EXIT_HALT
    return 0
```

Register the subcommand in `build_parser`:

```python
    check = sub.add_parser("check", help="halt if a declared ceiling is breached")
    check.add_argument("--started-at", type=float, required=True, dest="started_at")
    check.add_argument("--spend-usd", type=float, default=0.0, dest="spend_usd")
    check.set_defaults(fn=cmd_check)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /Users/mo/github/personal/Aviary-BioSim/.claude/skills/v2r-loop/scripts && uv run --with pytest --with pyyaml pytest tests/test_register_ceilings.py -v`

Expected: PASS, 6 passed

- [ ] **Step 5: Commit**

```bash
cd /Users/mo/github/personal/Aviary-BioSim
git add .claude/skills/v2r-loop/scripts/
"$AIADLC/tools/git-safe-commit" "feat(v2r-loop): ceilings halt the drain; attempts park a unit" --no-work-item --staged
```

---

### Task 7: Run record, instinct pin, and replay determinism

**Files:**
- Modify: `.claude/skills/v2r-loop/scripts/register.py`
- Test: `.claude/skills/v2r-loop/scripts/tests/test_register_record.py`

**Interfaces:**
- Consumes: `git`, `load`, `save` from Tasks 1–2.
- Produces: `instinct_pin() -> str | None` (the git tree SHA of `.aiadlc/instincts`, or `None` when the store does not exist yet), `cmd_pin(args) -> int`, `cmd_drain_start(args) -> int`, `cmd_drain_end(args) -> int` writing `.v2r/run-record-<drain>.yaml` with keys `drain`, `register_sha`, `instinct_pin`, `seed`, `ceilings`, `closed`, `parked`, `outcome`.

Per ADR-0003 the pin reuses the in-repo `.aiadlc/instincts` store and records its tree SHA. That SHA does **not** identify the instinct set exactly: hook reinforcement rewrites instinct frontmatter, so it moves when nothing was learned (corrected after drain 1 — see ADR-0003's correction and the flagged ambiguity in `docs/CONTEXT.md`).

**A deliberate narrowing of the spec's testing claim.** The spec asks that "a drain replays:
same register, same instinct pin, same seed → same closed and parked sets." That cannot be
asserted in a test, because a drain's work is done by LLM subagents and is not deterministic
at the token level. What the run record delivers, and what Task 7 actually tests, is
**attributability**: any drain's result is pinned to an exact register digest and a seed, and
labelled with the instinct tree SHA, which identifies the instinct set only approximately
(corrected after drain 1, see ADR-0003). A changed digest or seed explains a divergence; an
unchanged pair does not rule out instinct, prompt or builder variation. Determinism of the *record* is testable; determinism of the *builder* is not, and
claiming otherwise in a test would be theatre. The end-to-end invariant that Task 10 does
assert — every commit on the branch is green — is the one that actually protects the branch.

- [ ] **Step 1: Write the failing test**

Create `.claude/skills/v2r-loop/scripts/tests/test_register_record.py`:

```python
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import register  # noqa: E402


def test_instinct_pin_is_none_before_any_instinct_exists(git_repo):
    assert register.instinct_pin() is None


def test_instinct_pin_is_the_tree_sha_of_the_store(git_repo):
    store = git_repo / ".aiadlc" / "instincts"
    store.mkdir(parents=True)
    (store / "prefer-uv-run.md").write_text("always invoke via uv run\n")
    register.git("add", "-A")
    register.git("commit", "-q", "-m", "add instinct")

    pin = register.instinct_pin()
    assert pin == register.git("rev-parse", "HEAD:.aiadlc/instincts")


def test_instinct_pin_changes_when_the_store_changes(git_repo):
    store = git_repo / ".aiadlc" / "instincts"
    store.mkdir(parents=True)
    (store / "one.md").write_text("first\n")
    register.git("add", "-A")
    register.git("commit", "-q", "-m", "one")
    first = register.instinct_pin()

    (store / "two.md").write_text("second\n")
    register.git("add", "-A")
    register.git("commit", "-q", "-m", "two")

    assert register.instinct_pin() != first


def test_drain_end_writes_a_run_record(git_repo, register_data):
    register.V2R_DIR.mkdir()
    register_data["units"][0]["state"] = "parked"
    register.save(register.REGISTER, register_data)

    assert register.main(["drain-end", "--outcome", "completed"]) == 0

    record = yaml.safe_load((register.V2R_DIR / "run-record-1.yaml").read_text())
    assert record["drain"] == 1
    assert record["seed"] == 1337
    assert record["closed"] == ["U-002"]
    assert record["parked"] == ["U-001"]
    assert record["outcome"] == "completed"
    assert record["register_sha"].startswith("sha256:")


def test_run_record_is_stable_for_identical_register_state(git_repo, register_data):
    register.V2R_DIR.mkdir()
    register.save(register.REGISTER, register_data)
    register.main(["drain-end", "--outcome", "completed"])
    first = yaml.safe_load((register.V2R_DIR / "run-record-1.yaml").read_text())

    register.main(["drain-end", "--outcome", "completed"])
    second = yaml.safe_load((register.V2R_DIR / "run-record-1.yaml").read_text())

    assert first["register_sha"] == second["register_sha"]
    assert first["closed"] == second["closed"]
    assert first["parked"] == second["parked"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /Users/mo/github/personal/Aviary-BioSim/.claude/skills/v2r-loop/scripts && uv run --with pytest --with pyyaml pytest tests/test_register_record.py -v`

Expected: FAIL with `AttributeError: module 'register' has no attribute 'instinct_pin'`

- [ ] **Step 3: Write the minimal implementation**

In `register.py`, add above `build_parser`:

```python
INSTINCT_STORE = ".aiadlc/instincts"


def instinct_pin() -> str | None:
    """Tree SHA of the instinct store — an exact, already-versioned identifier.

    See ADR-0003: the store is in-repo and not gitignored, so the pin needs no
    new machinery. Returns None before any instinct has been captured.
    """
    try:
        return git("rev-parse", f"HEAD:{INSTINCT_STORE}")
    except subprocess.CalledProcessError:
        return None


def register_sha() -> str:
    return "sha256:" + hashlib.sha256(REGISTER.read_bytes()).hexdigest()


def cmd_pin(args) -> int:
    print(instinct_pin() or "")
    return 0


def cmd_drain_start(args) -> int:
    data = load(REGISTER)
    data["run"]["drain"] = args.drain
    data["run"]["seed"] = args.seed
    data["run"]["instinct_pin"] = instinct_pin()
    save(REGISTER, data)
    print(f"drain {args.drain} seed {args.seed} pin {data['run']['instinct_pin']}")
    return 0


def cmd_drain_end(args) -> int:
    data = load(REGISTER)
    record = {
        "drain": data["run"]["drain"],
        "register_sha": register_sha(),
        "instinct_pin": data["run"]["instinct_pin"],
        "seed": data["run"]["seed"],
        "ceilings": data["run"]["ceilings"],
        "closed": [u["id"] for u in data["units"] if u["state"] == CLOSED],
        "parked": [u["id"] for u in data["units"] if u["state"] == PARKED],
        "outcome": args.outcome,
    }
    save(V2R_DIR / f"run-record-{record['drain']}.yaml", record)
    print(f"drain {record['drain']} {args.outcome}: "
          f"{len(record['closed'])} closed, {len(record['parked'])} parked")
    return 0
```

Register the subcommands in `build_parser`:

```python
    start = sub.add_parser("drain-start", help="pin the instinct set and open a drain")
    start.add_argument("--drain", type=int, required=True)
    start.add_argument("--seed", type=int, required=True)
    start.set_defaults(fn=cmd_drain_start)

    end = sub.add_parser("drain-end", help="write the run record")
    end.add_argument("--outcome", choices=["completed", "halted"], required=True)
    end.set_defaults(fn=cmd_drain_end)

    sub.add_parser("pin", help="print the instinct pin").set_defaults(fn=cmd_pin)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /Users/mo/github/personal/Aviary-BioSim/.claude/skills/v2r-loop/scripts && uv run --with pytest --with pyyaml pytest tests/test_register_record.py -v`

Expected: PASS, 5 passed

- [ ] **Step 5: Commit**

```bash
cd /Users/mo/github/personal/Aviary-BioSim
git add .claude/skills/v2r-loop/scripts/
"$AIADLC/tools/git-safe-commit" "feat(v2r-loop): run record and instinct pin from the git tree SHA" --no-work-item --staged
```

---

### Task 8: Weave spans so stage 4 has something to read

Known gap 1 in the spec: Weave auto-traces SDK calls, and Claude Code subagents are not SDK calls. Without this task, `query_weave_traces_tool` returns nothing and the between-drain analysis has no input.

**Files:**
- Modify: `.claude/skills/v2r-loop/scripts/register.py`
- Test: `.claude/skills/v2r-loop/scripts/tests/test_register_trace.py`

**Interfaces:**
- Consumes: `cmd_close`, `cmd_park` from Tasks 3 and 5.
- Produces: `emit_span(name: str, **attrs) -> None`. It is a no-op when `weave` is not importable or `WANDB_API_KEY` is unset, so tests and offline runs never fail on telemetry.

- [ ] **Step 1: Write the failing test**

Create `.claude/skills/v2r-loop/scripts/tests/test_register_trace.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import register  # noqa: E402


def test_emit_span_is_a_noop_without_credentials(monkeypatch, capsys):
    monkeypatch.delenv("WANDB_API_KEY", raising=False)
    register.emit_span("unit.close", unit="U-001", attempts=1)
    assert capsys.readouterr().err == ""


def test_emit_span_reports_a_dropped_span_once(monkeypatch, capsys):
    monkeypatch.setenv("WANDB_API_KEY", "fake")
    monkeypatch.setattr(register, "_SPAN_SINK", None)
    monkeypatch.setattr(register, "_SPAN_WARNED", False)
    monkeypatch.setitem(sys.modules, "weave", None)  # `import weave` then raises

    register.emit_span("unit.close", unit="U-001")
    register.emit_span("unit.close", unit="U-002")

    err = capsys.readouterr().err
    assert "weave span dropped" in err
    assert err.count("weave span dropped") == 1


def test_emit_span_records_when_a_sink_is_installed(monkeypatch):
    captured = []
    monkeypatch.setattr(register, "_SPAN_SINK", captured.append)
    register.emit_span("unit.park", unit="U-014", attempts=3)
    assert captured == [{"name": "unit.park", "unit": "U-014", "attempts": 3}]


def test_close_emits_a_span(monkeypatch, git_repo, register_data):
    captured = []
    monkeypatch.setattr(register, "_SPAN_SINK", captured.append)
    register.V2R_DIR.mkdir()
    sealed = git_repo / "tests" / "sealed" / "v2r"
    sealed.mkdir(parents=True)
    (sealed / "test_u001.py").write_text("def test_ok():\n    assert True\n")
    register_data["units"][0]["state"] = "claimed"
    register_data["units"][0]["pre_claim_sha"] = register.head_sha()
    register.save(register.REGISTER, register_data)

    register.main(["close", "U-001"])

    assert any(span["name"] == "unit.close" for span in captured)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /Users/mo/github/personal/Aviary-BioSim/.claude/skills/v2r-loop/scripts && uv run --with pytest --with pyyaml pytest tests/test_register_trace.py -v`

Expected: FAIL with `AttributeError: module 'register' has no attribute 'emit_span'`

- [ ] **Step 3: Write the minimal implementation**

In `register.py`, add `import os` to the imports and this above `cmd_close`:

```python
_SPAN_SINK = None  # tests install a callable here; production resolves weave lazily
_SPAN_WARNED = False


def emit_span(name: str, **attrs) -> None:
    """Record one iteration span.

    Never raises — a drain must not die on telemetry. But it does not fail
    silently either: a dropped span means stage 4 has no evidence to read, so
    the first failure is reported once on stderr.
    """
    global _SPAN_WARNED
    payload = {"name": name, **attrs}
    if _SPAN_SINK is not None:
        _SPAN_SINK(payload)
        return
    if not os.environ.get("WANDB_API_KEY"):
        return
    try:
        import weave

        weave.init(os.environ.get("WANDB_PROJECT", "3m-m/Aviary-BioSim"))
        weave.publish(payload, name=name)
    except Exception as exc:  # noqa: BLE001 — telemetry is never load-bearing
        if not _SPAN_WARNED:
            print(f"weave span dropped ({type(exc).__name__}: {exc}); "
                  f"stage 4 will have no evidence for this drain", file=sys.stderr)
            _SPAN_WARNED = True
        return
```

In `cmd_close`, emit a span on each of the three exit paths, immediately before each `return`:

```python
    # before `return EXIT_HALT`
    emit_span("unit.halt", unit=unit["id"], reason="gate-unexecutable", pytest_exit=code)

    # before `return EXIT_TEST_FAILED`
    emit_span("unit.attempt", unit=unit["id"], attempts=unit["attempts"], output=output[-2000:])

    # before `return EXIT_CLOSED`
    emit_span("unit.close", unit=unit["id"], satisfies=unit["satisfies"], attempts=unit["attempts"])
```

In `cmd_park`, emit a span immediately before its `return 0`:

```python
    emit_span("unit.park", unit=unit["id"], attempts=unit["attempts"], branch=branch)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /Users/mo/github/personal/Aviary-BioSim/.claude/skills/v2r-loop/scripts && uv run --with pytest --with pyyaml pytest tests/ -v`

Expected: PASS, 33 passed

- [ ] **Step 5: Commit**

```bash
cd /Users/mo/github/personal/Aviary-BioSim
git add .claude/skills/v2r-loop/scripts/
"$AIADLC/tools/git-safe-commit" "feat(v2r-loop): emit weave spans per iteration so stage 4 has evidence" --no-work-item --staged
```

---

### Task 9: The skill itself

**Files:**
- Create: `.claude/skills/v2r-loop/SKILL.md`

**Interfaces:**
- Consumes: every `register.py` subcommand from Tasks 1–8: `status next claim seal close park check drain-start drain-end pin`.
- Produces: the `/v2r-loop` skill, taking exactly one argument.

- [ ] **Step 1: Write the skill**

Create `.claude/skills/v2r-loop/SKILL.md`:

````markdown
---
name: v2r-loop
description: Vision to reality. Takes a single free-text vision and carries it to a reviewed branch of working, individually-tested code. An attended head aligns the vision — researching open questions, grilling it until its boundary is decided, fixing the domain language, writing the spec, planning the implementation, and emitting a committed interface skeleton — which you approve once, declaring the ceilings the run may spend. An unattended body then drains it one build unit at a time, each written by an implementer that never sees its test and tested by an author that never sees the implementation, each close earned by a gate that re-runs the test itself. Failed units are reverted out of the tree and preserved on a branch, so the drain never leaves broken code behind. Between drains it reads its own execution traces, captures what it learned, and retries only what failed, stopping when it stops improving. Never writes the trunk, never lands its own PR, and cannot widen its scope after approval. Use when a vision needs building out end to end and you want to be involved once rather than continuously.
argument-hint: "<vision>"
---

# /v2r-loop — vision to reality

**Input:** `$ARGUMENTS` — the vision. The only parameter. No flags.

Spec: `docs/spec.md`
Glossary: `docs/CONTEXT.md` — use its vocabulary exactly.
Decisions: `docs/adr/0001`–`0004`.

```bash
R="uv run --with pyyaml .claude/skills/v2r-loop/scripts/register.py"
```

## Stage 0 — Preflight and unblock

Resolve access from available credentials and MCP servers. Report any blocker you cannot
resolve and **stop before the gate** — never work around one, never ask mid-drain.

| Blocker | Where it resolves |
|---|---|
| Inference compute | W&B Inference (serverless — no GPU on the critical path) |
| `WANDB_API_KEY` | Infisical `biofm/dev`, or `.env` |
| Trace read | `wandb` MCP server |

Confirm you are in a worktree whose branch is **not** `main`. If you are on `main`, stop.

## Stage 1 — Alignment (attended)

A vision is not a specification. Close that gap in order:

1. **`/research`** — ground the open questions. Skip when the vision stands on
   well-understood ground.
2. **`/grill-with-docs`** — one question at a time until the boundary is decided and every
   fuzzy term is sharpened against the glossary. Update `CONTEXT.md` inline; write an ADR
   when a decision is hard to reverse, surprising, and a real trade-off. **Terminology
   collisions caught here cost a sentence; caught in the register they cost a drain.**
3. **`spec.md`** — standing requirements `R<n>`. Never closed.
4. **`/writing-plans`** — the ordered implementation plan.
5. **`register.yaml` + `skeleton/`** — decompose the plan into build units `U-nnn`, each
   carrying `satisfies: R<n>`; emit real modules with real signatures and
   `NotImplementedError` bodies, one stub per unit. Commit the skeleton.

## Stage 2 — The gate (the last human checkpoint)

Present the aligned set and stop. Approval fixes scope permanently, declares the ceilings,
and grants standing authorization to push the branch and open a PR. **Do not proceed without
it.**

## Stage 3 — Drain (unattended)

```bash
$R drain-start --drain <n> --seed <n>
while unit=$($R next); do
  $R check --started-at "$START" || break        # exit 3 = halt the drain
  $R claim "$unit"
  # test-author subagent: sealed test from the unit statement + skeleton ONLY
  $R seal "$unit"
  # implementer subagent: fill the stub; never shown the sealed test
  $R close "$unit"                               # 0 closed · 1 retry · 3 HALT
done
$R drain-end --outcome completed
```

- Dispatch **two separate subagents** per unit. The test-author is given the unit statement
  and the skeleton; the implementer is given the unit statement and the stub. Neither sees
  the other's output.
- `close` returning **1** means retry, up to `max_attempts`. Then:
  `$R park "$unit" --evidence <pytest output>`.
- `close` returning **3** is a **halt**, not a park. Stop the drain.
- A park is local. Do not infer that any other unit is blocked. Do not add `blocked_by`.

At drain end, push the branch and `gh pr create`. **Never write `main`. Never land the PR** —
hand it to the CTO.

## Stage 4 — Between drains

1. `query_weave_traces_tool` over this drain's spans — which units parked, at which attempt,
   on what failure.
2. `instinct capture` per durable lesson, with the drain's touched paths as `--triggers`.
3. Commit `.aiadlc/instincts`; the new pin is `$R pin`.
4. Drain *n+1* retries **only parked units**.

Stop when a drain closes zero new units, or `max_drains` is reached. Report the parked list.

## Never

- Write `main`, or land a PR.
- Add a build unit that was not in the approved register.
- Assert a close. Only `register.py close` closes a unit.
- Show the implementer the sealed test, or the test-author the implementation.
````

- [ ] **Step 2: Verify the skill is discoverable**

Run: `cd /Users/mo/github/personal/Aviary-BioSim && ls .claude/skills/v2r-loop/SKILL.md && head -3 .claude/skills/v2r-loop/SKILL.md`

Expected: the file exists and begins with `---` followed by `name: v2r-loop`.

- [ ] **Step 3: Commit**

```bash
cd /Users/mo/github/personal/Aviary-BioSim
git add .claude/skills/v2r-loop/SKILL.md
"$AIADLC/tools/git-safe-commit" "feat(v2r-loop): the skill — one vision parameter, stages 0-4" --no-work-item --staged
```

---

### Task 10: End-to-end drain against a fixture register

Proves the invariant that the whole design rests on: **every commit on the branch is green.**

**Files:**
- Test: `.claude/skills/v2r-loop/scripts/tests/test_drain_end_to_end.py`

**Interfaces:**
- Consumes: every `register.py` command.
- Produces: nothing — this is the acceptance test.

- [ ] **Step 1: Write the failing test**

Create `.claude/skills/v2r-loop/scripts/tests/test_drain_end_to_end.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import register  # noqa: E402


def _fixture_drain(git_repo, register_data):
    """One satisfiable unit, one deliberately unsatisfiable one."""
    register.V2R_DIR.mkdir()
    sealed = git_repo / "tests" / "sealed" / "v2r"
    sealed.mkdir(parents=True)
    (sealed / "test_u001.py").write_text("def test_ok():\n    assert True\n")
    (sealed / "test_u002.py").write_text("def test_never():\n    assert False\n")
    register_data["units"][1]["state"] = "open"
    register_data["units"][1]["attempts"] = 0
    register.save(register.REGISTER, register_data)


def test_drain_closes_what_it_can_and_parks_the_rest(git_repo, register_data):
    _fixture_drain(git_repo, register_data)
    register.main(["drain-start", "--drain", "1", "--seed", "1337"])

    while (unit_id := register.next_open(register.load(register.REGISTER))):
        register.main(["claim", unit_id])
        register.main(["seal", unit_id])
        data = register.load(register.REGISTER)
        unit = register.unit_by_id(data, unit_id)
        while register.main(["close", unit_id]) == 1:
            data = register.load(register.REGISTER)
            unit = register.unit_by_id(data, unit_id)
            if register.attempts_exhausted(unit, data):
                (register.V2R_DIR / "ev.out").write_text("failed\n")
                register.main(["park", unit_id, "--evidence", str(register.V2R_DIR / "ev.out")])
                break

    register.main(["drain-end", "--outcome", "completed"])

    data = register.load(register.REGISTER)
    assert register.unit_by_id(data, "U-001")["state"] == "closed"
    assert register.unit_by_id(data, "U-002")["state"] == "parked"


def test_every_commit_on_the_branch_is_green(git_repo, register_data):
    _fixture_drain(git_repo, register_data)
    register.main(["drain-start", "--drain", "1", "--seed", "1337"])
    register.main(["claim", "U-001"])
    register.main(["seal", "U-001"])
    register.main(["close", "U-001"])

    subjects = register.git("log", "--pretty=%s").splitlines()
    assert any(s.startswith("U-001") for s in subjects)
    assert not any("parked attempt" in s for s in subjects)
```

- [ ] **Step 2: Run the tests to verify they fail or pass**

Run: `cd /Users/mo/github/personal/Aviary-BioSim/.claude/skills/v2r-loop/scripts && uv run --with pytest --with pyyaml pytest tests/test_drain_end_to_end.py -v`

Expected: PASS if Tasks 1–8 are correct. If either test fails, the bug is in an earlier task — fix it there, not here.

- [ ] **Step 3: Run the whole suite**

Run: `cd /Users/mo/github/personal/Aviary-BioSim/.claude/skills/v2r-loop/scripts && uv run --with pytest --with pyyaml pytest tests/ -v`

Expected: PASS, 35 passed

- [ ] **Step 4: Commit**

```bash
cd /Users/mo/github/personal/Aviary-BioSim
git add .claude/skills/v2r-loop/scripts/tests/test_drain_end_to_end.py
"$AIADLC/tools/git-safe-commit" "test(v2r-loop): end-to-end drain proves the green-commit invariant" --no-work-item --staged
```
