#!/usr/bin/env python3
"""Stands in for the Codex CLI so the work handoff can be driven for free.

Records every invocation as one JSON line in $CODEX_STUB_CALLS, then behaves
according to $CODEX_STUB_MODE:

    ok        write the completion report, print a summary, exit 0
    noreport  print a summary and exit 0 WITHOUT writing the report (a
              receiver that replied early and did nothing)
    fail      print an error and exit 1
    slow      sleep long enough to trip any short --timeout
"""

import json
import os
import re
import sys
import time


def main() -> int:
    with open(os.environ["CODEX_STUB_CALLS"], "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd()}) + "\n")

    mode = os.environ.get("CODEX_STUB_MODE", "ok")
    if mode == "slow":
        time.sleep(10)
    if mode == "fail":
        print("stub: something broke", file=sys.stderr)
        return 1
    if mode == "ok":
        match = re.search(r"completion report to (\S+)", sys.argv[-1])
        if match:
            with open(match.group(1), "w", encoding="utf-8") as handle:
                handle.write("stub completion report\n")
    print("Completed: the next steps. Remaining: none. Verification: checks pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
