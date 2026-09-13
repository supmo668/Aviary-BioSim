---
name: v2r-gate-env-needs-every-sealed-test-import
confidence: 0.900
created: 2026-09-13T18:49:55Z
last_reinforced: 2026-09-13T18:56:40Z
ttl_days: 30
triggers: [.claude/skills/v2r-loop/scripts/register.py, .claude/skills/v2r-loop/SKILL.md]
tags: [v2r-loop, tooling]
---

register.py runs the sealed test as sys.executable -m pytest, where sys.executable is the interpreter uv built for register.py itself — NOT the project env. Every import a sealed test needs must therefore be in the $R invocation: uv run --with pyyaml --with weave --with fhaviary .../register.py. Miss one and run_sealed_test returns HALT (collection error), which stops the entire drain rather than failing one unit. weave is the sneaky one: it is needed by emit_span, not by any test, and without it every span is silently dropped after a single stderr warning.
