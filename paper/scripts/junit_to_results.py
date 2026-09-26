#!/usr/bin/env python3
"""Turn pytest's junit report into the referee's dialect. Used by sealed_suite_results.sh.

Prints `PLAN <n>` then one `RESULT pass|fail|skip <classname/name>` per testcase and a
trailing comment naming the archived commit. Prints NOTHING and exits 3 when the report
holds zero testcases or cannot be parsed — a report with no results is "could not run",
never a pass. No assertion text is ever printed.
"""
import sys
import xml.etree.ElementTree as ET


def results(xml_path: str):
    root = ET.parse(xml_path).getroot()
    out = []
    for tc in root.iter("testcase"):
        cat = tc.get("classname", "").split(".")[-1] + "/" + tc.get("name", "")
        if tc.find("failure") is not None or tc.find("error") is not None:
            out.append(("fail", cat))
        elif tc.find("skipped") is not None:
            out.append(("skip", cat))
        else:
            out.append(("pass", cat))
    return out


def main(argv) -> int:
    if len(argv) != 3:
        print("COULD-NOT-RUN: usage: junit_to_results.py <junit.xml> <commit>", file=sys.stderr)
        return 3
    try:
        rs = results(argv[1])
    except (ET.ParseError, OSError) as exc:
        print(f"COULD-NOT-RUN: junit report unreadable ({type(exc).__name__})", file=sys.stderr)
        return 3
    if not rs:
        print(f"COULD-NOT-RUN: the junit report holds zero testcases at {argv[2]}", file=sys.stderr)
        return 3
    print(f"PLAN {len(rs)}")
    for verdict, cat in rs:
        print(f"RESULT {verdict} {cat}")
    print(f"# archived commit {argv[2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
