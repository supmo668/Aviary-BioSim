---
name: a-guard-that-only-sees-its-own-artifacts-tests-the-defender
confidence: 0.950
created: 2026-09-24T18:58:33Z
last_reinforced: 2026-09-24T18:58:33Z
ttl_days: 30
triggers: [science/tests/conftest.py, conftest.py, pytest_runtest_setup, sys.modules, validation]
tags: [testing, security, detection, method]
---

A guard that recognises only the artifacts its own side creates tests the DEFENDER, not the THREAT. It will be green forever, and green for the wrong reason.

Found twice in one unit, both mine:

1. A test-isolation guard detected fake modules by a marker attribute the conftest itself set on every fake it built. It therefore caught every stub written by that file — and missed the contributor who writes sys.modules["torch"] = Mock() having never heard of the marker, which is the entire population the guard existed to stop. Two reviewers proved it passed green with a fake live for a whole session. The fix was detection by IDENTITY: snapshot what each watched name held before collection, and compare. Identity describes the property; a marker describes only the artifacts you remembered to label.

2. Same shape one level up: a meta-test meant to exercise that guard installed a shim with "from conftest import *", which resolved to pytest's own generated conftest rather than the suite's. No hooks registered, the probe ran unguarded, and the meta-test passed without ever touching the thing it tested. A test of a guard that does not exercise the guard is indistinguishable from a passing test — only a mutant on the shim exposes it.

The same move appears in validation: refusing at a published GRAMMAR rather than at a character class I enumerated. Both replace "the things I thought to list" with "the property itself".

Rule: when building a detector, ask which population it can see. If the answer is "the ones my own code marked / created / registered", it is measuring cooperation, not compliance. Prefer identity, invariants and snapshots over cooperative markers, allowlists and registration. And prove a detector by constructing the hostile case it is meant to catch — written by someone who never read your code — not by the friendly one you already produce.
