---
name: shell-gate-must-test-the-property-not-the-exit-code
confidence: 0.900
created: 2026-09-17T09:13:23Z
last_reinforced: 2026-09-17T09:13:23Z
ttl_days: 30
triggers: [git-safe-commit, git commit, grep, git grep, &&]
tags: [shell, commit-discipline, verification, defect]
---

Two commits in one session carried messages that described states the evidence did not show. Both were shell-chaining failures, and both are the same shape as every other finding that week: a step reports success while the property it is meant to guarantee is absent.

1. ';' LETS THE COMMIT RUN AFTER A FAILED STEP. 'patch ; test ; git-safe-commit' ran the commit after the patch step died with a SyntaxError (the patch was a heredoc whose quoting broke). The test run even printed '1 failed' — and the commit, whose message claimed the fix, went in anyway, leaving the branch red. Chain verification-then-commit with '&&', and make the test step itself fail the chain: capture output and require the exact pass line (e.g. OUT=$(pytest ... | tail -1) && echo "$OUT" | grep -q '^42 passed'), because a pipeline's exit status is the last command's, not pytest's.

2. GREP'S EXIT CODE IS INVERTED FOR A 'NOTHING LEFT' CHECK. 'git grep PATTERN && git commit -m "sweep clean"' commits exactly when the sweep FOUND matches: grep exits 0 on a match and 1 on no match. The sweep printed three surviving overclaims and the commit claimed none remained. For an absence check, capture the output and gate on emptiness: HITS=$(git grep -n PATTERN; true) && [ -z "$HITS" ] && commit.

3. PUT MULTI-LINE EDITS IN A SCRIPT FILE, NOT AN INLINE HEREDOC WITH NESTED QUOTES. Triple-quoted Python inside a bash heredoc is where the first failure came from. Write the patch to a file, run it, assert each anchor matched exactly once.

General rule: a commit message is a claim. Gate it on the observed property (tests passed with the expected count; sweep output is empty; the documented command runs verbatim), never on 'the previous command exited 0'. And before correcting a bad commit, check whether it was pushed; if not, add a corrective commit whose message says what the earlier one got wrong — do not rewrite history to hide it.
