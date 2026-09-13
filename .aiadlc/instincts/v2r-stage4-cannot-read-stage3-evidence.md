---
name: v2r-stage4-cannot-read-stage3-evidence
confidence: 1.000
created: 2026-09-13T18:49:53Z
last_reinforced: 2026-09-13T18:56:40Z
ttl_days: 30
triggers: [.claude/skills/v2r-loop/scripts/register.py, .claude/skills/v2r-loop/SKILL.md, emit_span, weave]
tags: [v2r-loop, observability, defect, fixed]
---

FIXED after drain 1 — but the lesson is the durable part, not the fix.

`weave.publish(payload, name=...)` writes a weave OBJECT. Objects and calls are different
stores, and `query_weave_traces_tool` sees only calls. So a drain that published every span
perfectly returned `total_count 0` for stage 4's own documented query.

The fix: a `@weave.op`-decorated function named for the transition, invoked once per span, so
`op_name` is `unit.close` / `unit.park` / `unit.halt` and the call is queryable. Verified by
querying back, not by reading code.

Two lessons that outlive the bug:

1. INSTRUMENTED AND READABLE ARE DIFFERENT PROPERTIES. Verify telemetry by querying it back,
   never by inspecting the emitting code. `publish` succeeded and printed a confident URL the
   entire time it was writing evidence nothing could read.
2. `docs/spec.md` ALREADY PRESCRIBED `@weave.op` spans and the implementation used `publish`
   instead. Nothing caught the drift, because the wrong call also "worked". When a spec names
   a mechanism, the test should assert the mechanism's observable consequence, not that the
   code ran.

Drain 1's six closes remain objects and are reachable only via `weave.init()` +
`client._objects()` + `weave.ref(...).get()`. Do NOT re-emit them as calls — that fabricates
trace evidence with the wrong timestamps, asserted rather than observed.

Tooling note: `instinct capture` on an existing name only REINFORCES it; it does not replace
the body. To correct an instinct's text, edit the file.
