---
name: v2r-commit-between-units-never-inside
confidence: 0.850
created: 2026-09-13T18:49:54Z
last_reinforced: 2026-09-13T18:49:54Z
ttl_days: 30
triggers: [.claude/skills/v2r-loop/scripts/register.py, .v2r/register.yaml, park]
tags: [v2r-loop, git, park]
---

Never make an unrelated commit while a build unit is CLAIMED. park does: git add -A; git commit; git branch -f park/U-nnn; git reset --hard pre_claim_sha. reset --hard moves the BRANCH POINTER back, so every commit made after that unit was claimed leaves the working branch and survives only on park/U-nnn, where nobody will look for it. A doc fix, a config tweak or a dependency bump made mid-unit is therefore hostage to that unit parking. Do housekeeping commits in the window between a close and the next claim, never inside one.
