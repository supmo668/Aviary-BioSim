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

4. QUOTING: A DOUBLE-QUOTED ARGUMENT SILENTLY EATS BACKTICKS AND $. This applies to EVERY long
   text passed on a command line — dispatch bodies AND git-safe-commit --body alike; it bit me
   once in each. Sending a body as
   "$BODY" or as a double-quoted literal ran its backticked phrase as command substitution: the
   shell printed 'command not found', substituted empty, and the send still reported success — a
   message delivered with text I never wrote. USE `dispatch create --body-file <path>` — it reads the
   body with zero shell interpolation. It exists in 0.56.0-0.60.0 but is MISSING from the tool's
   usage line, which is why it is easy to miss; `--body-file -` also reads stdin. Failing that, a
   single-quoted heredoc (BODY=$(cat <<'EOF' ... EOF)). Either way, read the written artifact back
   before trusting the ✓.

   DO NOT rely on dispatch's metacharacter warning: it is ANTI-CORRELATED with the fault. It fires
   when metachars are still PRESENT, i.e. when quoting worked; when substitution already consumed
   them the body is wrong and the warning is silent. Its silence reads as assurance and means the
   opposite.

5. A PIPELINE'S EXIT STATUS IS THE LAST COMMAND'S, SO `| head` SWALLOWS grep's NO-MATCH SIGNAL.
   `grep -q X f | head -2 || echo "(not found)"` exits 0 and the `||` branch never fires: the
   search reports nothing and looks like success. This produced a FALSE NEGATIVE about a
   capability — I concluded `--body-file` did not exist when it did. Never pipe a search whose
   exit status you intend to test; capture it first (HITS=$(grep ... ; true)) and branch on the
   captured value.

6. A DIAGNOSTIC LABEL MUST BE CONDITIONAL ON WHAT IT REPORTS. `grep -rl X ... | head; echo "(only
   dispatches = agent is right)"` prints its conclusion whatever grep found, so the label can
   overwrite the evidence that contradicts it. Print the verdict from the captured result, never
   beside it. (Both sides of this exchange committed this one on the same day.)

7. MUTATION TESTING LEAVES STALE __pycache__, AND THE RESTORE CHECK DOES NOT CATCH IT. Editing a
   module in place, running the suite, then restoring it with `cp` can leave a .pyc compiled from
   the MUTANT. Python reuses a .pyc when the source's recorded mtime and size match, and a
   mutate-run-restore cycle inside one second can satisfy both — so the next run executes the
   mutant while the file on disk is correct. Observed: two tests failed against a source that was
   demonstrably right, and `inspect.getsource` showed the CORRECT body because it reads the FILE,
   not the loaded code object. Comparing the restored source with the backup (`cmp`) does not
   detect it either, because the source is genuinely identical; the divergence is in the cache.
   Run mutants with `python -B` / PYTHONDONTWRITEBYTECODE=1 and delete __pycache__ between
   mutations. Same family as the rest: the check verified an artifact ADJACENT to the thing that
   actually executes.

8. WHEN THE THING YOU ARE SEARCHING FOR IS THE THING YOU MUST NOT REPRODUCE, GREP FOR ITS
   LOCATION, NEVER ITS CONTENT. Checking whether a constraint is violated can violate it: the
   matching line lands in a transcript that is retained. Safe forms are `grep -c`, `grep -l`, and
   `grep -n ... | cut -d: -f1`; unsafe forms are `grep -n` printing the line and anything with
   -A/-B/-C. The unsafe ones are the ergonomic ones, which is why this has to be a rule and not a
   habit. Applies to secrets, credentials, PII, and any constraint about what must not be written
   down. Observed twice in one session, on both sides of a review.

General rule: a commit message is a claim. Gate it on the observed property (tests passed with the expected count; sweep output is empty; the documented command runs verbatim), never on 'the previous command exited 0'. And before correcting a bad commit, check whether it was pushed; if not, add a corrective commit whose message says what the earlier one got wrong — do not rewrite history to hide it.
