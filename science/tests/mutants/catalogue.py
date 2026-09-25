"""Every mutant used to gate this suite, frozen as data.

Four review passes each found real defects after the previous declared done. The
mutants those passes used are the only written record of what this suite's guards
must actually catch — a specification of the property, arrived at the expensive way.

They are frozen here BEFORE the guard is simplified, so "simplify" becomes a
measurable operation: the minimum guard that still kills every entry below. Without
this the simplification would quietly discard what three passes bought.

Each entry: apply `find` -> `replace` in `target`, run `check`, and the suite must
FAIL. A mutant that survives means the property it probes is no longer pinned.

`find` must occur EXACTLY ONCE in its target — test_mutant_catalogue.py asserts that
on every run, so an entry cannot silently stop applying when the code moves.
"""

# check: pytest arguments identifying the smallest set that should catch the mutant.
SCIENCE = "science/tests"
ENV = "science/tests/test_biosim_env_budget.py"
ESM = "science/tests/test_esm_tool_accession.py"
DISC = "science/tests/test_run_discovery_budget.py"
ISO = "science/tests/test_stub_isolation.py"

MUTANTS = [
    # --- budget enforcement (pass 1) ---
    dict(id="env-no-check", pass_="1", target="science/biosim_env.py", check=SCIENCE,
         why="step() must refuse before every tool call",
         find="            self.tracker.check()\n",
         replace=""),
    dict(id="env-check-once-per-batch", pass_="1", target="science/biosim_env.py", check=ENV,
         why="the refusal is per call, not per batch",
         find="        for call in valid.tool_calls:\n            # Refuse BEFORE",
         replace="        self.tracker.check()\n        for call in valid.tool_calls:\n            # Refuse BEFORE"),
    dict(id="env-spend-remaining-clamped", pass_="1", target="science/biosim_env.py", check=ENV,
         why="spend_remaining must not overstate what is left",
         find="        return self.tracker.ceiling_usd - self.tracker.total()",
         replace="        return max(0.0, self.tracker.ceiling_usd - self.tracker.total())"),
    dict(id="env-spend-remaining-writes", pass_="1", target="science/biosim_env.py", check=ENV,
         why="spend_remaining is read-only",
         find="        return self.tracker.ceiling_usd - self.tracker.total()",
         replace='        self.tracker.record("peek", 0.0)\n        return self.tracker.ceiling_usd - self.tracker.total()'),
    dict(id="env-charge-unvalidated", pass_="1", target="science/biosim_env.py", check=ENV,
         why="the harness ledger path rejects nonsense costs",
         find="        self.tracker.record(call_id, _valid_cost(cost_usd))",
         replace="        self.tracker.record(call_id, cost_usd)"),

    # --- accession validation (pass 2) ---
    dict(id="esm-no-validation", pass_="2", target="science/esm_tool.py", check=ESM,
         why="fetch_sequence validates before touching disk or network",
         find="    accession = valid_accession(accession)\n    CACHE.mkdir",
         replace="    CACHE.mkdir"),
    dict(id="esm-returns-callers-object", pass_="2", target="science/esm_tool.py", check=ESM,
         why="the validated TEXT is what flows on, not the caller's object",
         find="    return match.group(0)", replace="    return accession"),
    dict(id="esm-returns-str-of-caller", pass_="2", target="science/esm_tool.py", check=ESM,
         why="str() still calls a subclass's __str__",
         find="    return match.group(0)", replace="    return str(accession)"),
    dict(id="esm-grammar-narrowed", pass_="2", target="science/esm_tool.py", check=ESM,
         why="the 10-character accession branch is real",
         find="(?:[A-Z][A-Z0-9]{2}[0-9]){1,2}", replace="(?:[A-Z][A-Z0-9]{2}[0-9]){1,1}"),
    dict(id="esm-grammar-loosened", pass_="2", target="science/esm_tool.py", check=ESM,
         why="a character class is not the grammar",
         find='r"\\A(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})\\Z"',
         replace='r"\\A[A-Z0-9]{6,10}\\Z"'),
    dict(id="esm-url-hardcoded", pass_="2", target="science/esm_tool.py", check=ESM,
         why="the URL is derived from the accession, not a constant",
         find='f"https://rest.uniprot.org/uniprotkb/{accession}.fasta"',
         replace='"https://rest.uniprot.org/uniprotkb/P01308.fasta"'),
    dict(id="esm-no-cache-write", pass_="2", target="science/esm_tool.py", check=ESM,
         why="a fetched record is cached",
         find="    cached.write_text(json.dumps(rec, indent=2))\n", replace=""),
    dict(id="esm-echoes-cache-accession", pass_="3", target="science/esm_tool.py", check=ESM,
         why="tools report the validated accession, not the cache file's",
         find="        return f\"position {position} is outside {accession} (length {len(seq)})\"",
         replace="        return f\"position {position} is outside {rec['accession']} (length {len(seq)})\""),
    dict(id="esm-raw-organism", pass_="3", target="science/esm_tool.py", check=ESM,
         why="cache fields reaching the operator are stripped of control characters",
         find="({operator_safe(rec['organism'])}, ", replace="({rec['organism']}, "),
    dict(id="esm-raw-length", pass_="3", target="science/esm_tool.py", check=ESM,
         why="every cache field reaching the operator is stripped, not just one",
         find="{operator_safe(rec['length'])} aa", replace="{rec['length']} aa"),
    dict(id="esm-no-residue-guard", pass_="3", target="science/esm_tool.py", check=ESM,
         why="a cached sequence need not hold standard residues",
         find="    if wt not in AA:", replace="    if False:"),

    # --- harness metering (pass 1) ---
    dict(id="disc-conclusion-unmetered", pass_="1", target="science/run_discovery.py", check=DISC,
         why="the conclusion call is refused when over budget",
         find='            final = paid_turn(env, price, "conclusion", messages, schema)',
         replace="            final = agent_turn(messages, schema)"),
    dict(id="disc-results-by-position", pass_="1", target="science/run_discovery.py", check=DISC,
         why="results are paired to calls by id, not by position",
         find='    return [results.get(c["id"], "tool error: no response") for c in calls]',
         replace="    return list(results.values())"),
    dict(id="disc-no-charge", pass_="1", target="science/run_discovery.py", check=DISC,
         why="every model call reaches the ledger",
         find="    env.charge(call_id, tokens * price / 1_000_000)\n", replace=""),
    dict(id="disc-infinite-price", pass_="1", target="science/run_discovery.py", check=DISC,
         why="the declared price must be finite",
         find="    if not (math.isfinite(price) and price > 0):", replace="    if not (price > 0):"),

    # --- the isolation guard (passes 2-4) ---
    dict(id="guard-hooks-disabled", pass_="2", target="science/tests/conftest.py", check=ISO,
         why="the guard runs at all",
         find="@pytest.hookimpl(tryfirst=True)\ndef pytest_runtest_setup(item):",
         replace="@pytest.hookimpl(tryfirst=True)\ndef pytest_runtest_setup(item):\n    return"),
    dict(id="guard-marker-based", pass_="2", target="science/tests/conftest.py", check=ISO,
         why="detection is by identity, not by a marker only this file sets",
         find='    return [name for name in WATCHED if sys.modules.get(name) is not _BASELINE.get(name)]',
         replace='    return [name for name in WATCHED\n'
                 '            if getattr(sys.modules.get(name), "_conftest_fake", False)]'),
    dict(id="guard-trusts-dunder-file", pass_="3", target="science/tests/conftest.py", check=ISO,
         why="a fabricated __file__ is not identity",
         find='    """\n' + '    return [name for name in WATCHED if sys.modules.get(name) is not _BASELINE.get(name)]',
         replace='    """\n'
                 '    return [name for name in WATCHED\n'
                 '            if sys.modules.get(name) is not _BASELINE.get(name)\n'
                 '            and not str(getattr(sys.modules.get(name), "__file__", "")).endswith(".py")]'),
    dict(id="guard-no-shadow-detection", pass_="4", target="science/tests/conftest.py", check=ISO,
         why="a shadow that replaces a watched module is caught by identity; presence of the name is not enough",
         find="    fact that the object is not the one that was there before collection.\n"
              '    """\n' + '    return [name for name in WATCHED if sys.modules.get(name) is not _BASELINE.get(name)]',
         replace="    fact that the object is not the one that was there before collection.\n"
                 '    """\n'
                 "    return [name for name in WATCHED\n"
                 "            if (name in sys.modules) != (_BASELINE.get(name) is not None)]"),
    dict(id="guard-no-origin-baseline", pass_="4", target="science/tests/conftest.py", check=ISO,
         why="the baseline is the real module imported before collection, not whatever happened to be loaded",
         find="        for name in WATCHED:\n"
              "            try:\n"
              "                importlib.import_module(name)\n"
              "            except Exception:             # not installed, or needs one that is not\n"
              "                pass",
         replace="        for name in WATCHED:\n"
                 "            pass"),
    dict(id="guard-dotted-exempt", pass_="4", target="science/tests/conftest.py", check=ISO,
         why="a dotted name is watched, not exempted",
         find='           "aviary.core", "torch", "transformers", "requests",',
         replace='           "torch", "transformers", "requests",'),
    dict(id="guard-watched-shrunk", pass_="4", target="science/tests/conftest.py", check=ISO,
         why="every watched name is watched",
         find='WATCHED = ("esm_tool", "biosim_env", "run_discovery", "spend_tracker",',
         replace='WATCHED = ("esm_tool", "torch", "transformers", "requests")\n_UNUSED = ('),
    dict(id="guard-loader-keeps-syspath", pass_="3", target="science/tests/conftest.py", check=ISO,
         why="the by-path loader unwinds a module's sys.path write",
         find="        sys.path[:] = saved_for_loader", replace="        pass"),
    dict(id="guard-bio-raw-syspath", pass_="3", target="science/tests/conftest.py", check=ISO,
         why="fixtures prepend the path through monkeypatch so it unwinds",
         find="    monkeypatch.syspath_prepend(str(DEMO))",
         replace="    sys.path.insert(0, str(DEMO))"),
    dict(id="guard-bio-reads-sys-modules", pass_="3", target="science/tests/conftest.py", check=ISO,
         why="the bundle imports its classes rather than reading sys.modules",
         find="        from spend_tracker import BudgetExceeded",
         replace="        BudgetExceeded = sys.modules['spend_tracker'].BudgetExceeded"),
    dict(id="guard-budget-class-widened", pass_="2", target="science/tests/conftest.py", check=ISO,
         why="'the rollout STOPS' must not degrade to 'raises anything'",
         find="        self.BudgetExceeded = BudgetExceeded",
         replace="        self.BudgetExceeded = Exception"),
]
