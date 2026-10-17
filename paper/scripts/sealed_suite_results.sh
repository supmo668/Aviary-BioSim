#!/bin/sh
# paper/scripts/sealed_suite_results.sh — the tests.referee_command for this repository.
#
# Extracts the pass-end commit's WHOLE tree (the code and the independent tests exactly as
# they were when the pass closed), runs the suite there, and prints the referee's dialect:
# one `PLAN <n>` line and one `RESULT pass|fail|skip <category>` line per test. Nothing
# here prints assertion text; the category is the test's class and name.
#
# EXIT CODES — "could not run" is never allowed to look like "ran and failed":
#   0  the suite ran; PLAN + RESULT lines are on stdout (every result a pass or skip)
#   1  the suite ran and at least one RESULT is a fail
#   3  COULD NOT RUN — NOTHING on stdout; one `COULD-NOT-RUN: <what was missing>` line on
#      stderr. Missing tool, unknown commit, failed archive, missing suite directory,
#      pytest unable to start, no junit report, ZERO TESTS COLLECTED. To the referee,
#      which ignores exit codes, this shape is "no recognisable results" and it refuses
#      to sign; paper/scripts/record_referee.py reads the exit code directly.
set -u
COMMIT="${DRAIN1_END_COMMIT:-2e00aa3}"
SUITE="${SUITE_PATH:-demo/tests/sealed}"

die() { printf 'COULD-NOT-RUN: %s\n' "$*" >&2; exit 3; }

for tool in git tar uv python3; do
  command -v "$tool" >/dev/null 2>&1 || die "$tool is not on PATH"
done
# The script's own directory, by parameter expansion: no external command before the
# tool check above has said which tools exist.
case "$0" in */*) HERE="${0%/*}" ;; *) HERE="." ;; esac
git rev-parse --verify --quiet "$COMMIT^{commit}" >/dev/null 2>&1 \
  || die "commit $COMMIT is not in this repository"

WORK="$(mktemp -d 2>/dev/null)" || die "mktemp failed"
trap 'rm -rf "$WORK"' EXIT

git archive "$COMMIT" 2>/dev/null | tar -x -C "$WORK" 2>/dev/null
[ -d "$WORK/demo" ] || die "git archive of $COMMIT produced no demo/ tree"
[ -e "$WORK/$SUITE" ] || die "no test path '$SUITE' in the archived tree at $COMMIT"

# Every name the suite imports is DECLARED here, never left to arrive transitively (the
# A7b rule): the independent tests import the aviary package (fhaviary on PyPI).
( cd "$WORK" && uv run --with pytest --with pyyaml --with fhaviary python -B -m pytest "$SUITE" -q \
    -p no:cacheprovider --junitxml junit.xml >/dev/null 2>&1 )
PYRC=$?
# pytest: 0 all passed, 1 failures, 2 interrupted, 3 internal error, 4 usage, 5 no tests.
case "$PYRC" in
  0|1) ;;
  5) die "zero tests collected from '$SUITE' at $COMMIT" ;;
  *) die "pytest could not run the suite (exit $PYRC) at $COMMIT" ;;
esac
[ -s "$WORK/junit.xml" ] || die "pytest wrote no junit report"

python3 "$HERE/junit_to_results.py" "$WORK/junit.xml" "$COMMIT" || exit 3
[ "$PYRC" -eq 1 ] && exit 1
exit 0
