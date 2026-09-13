---
name: v2r-stage4-cannot-read-stage3-evidence
confidence: 0.900
created: 2026-09-13T18:49:53Z
last_reinforced: 2026-09-13T18:49:53Z
ttl_days: 30
triggers: [.claude/skills/v2r-loop/scripts/register.py, .claude/skills/v2r-loop/SKILL.md, emit_span, weave]
tags: [v2r-loop, observability, defect]
---

SKILL.md stage 4 says to read a drain's evidence with query_weave_traces_tool over unit.attempt/close/park/halt spans. That query returns ZERO for a drain that emitted evidence perfectly. emit_span calls weave.publish(payload, name=name), which creates a weave OBJECT, not a call/trace span — objects and traces are different stores, and the trace query never sees them. Verified on drain 1: count_weave_traces_tool reported total_count 0 while six unit.close objects sat in the project. Read them instead via the weave client: weave.init(project) then client._objects(), filter object_id, and weave.ref(f'weave:///{entity}/{project}/object/{object_id}:{digest}').get() for each payload. Note every close is a new VERSION of one object named unit.close, not six distinct objects. Either fix stage 4's instruction or make emit_span open a real call; until then, a drain that looks perfectly instrumented is unreadable by its own documented procedure.
