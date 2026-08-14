#!/usr/bin/env python3
"""Stands in for the Antigravity CLI so the handoff can be driven for free.

Records every invocation as one JSON line in $AGY_STUB_CALLS, then behaves
according to $AGY_STUB_MODE:

    all   commit every pending path (the cooperative case)
    one   commit a single path, leaving the rest (a partial handoff)
    first commit a single path on the first call, then stall on every later
          call (a per-unit run that dies mid-way)
    none  commit nothing and report a permission denial the way headless agy
          does — cleanly, on stdout, with exit code 0
"""

import json
import os
import subprocess
import sys
from pathlib import Path


def parse_args(argv):
    parsed = {}
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "-p":
            parsed["prompt"] = argv[index + 1]
            index += 2
        elif token.startswith("--"):
            parsed[token[2:].replace("-", "_")] = argv[index + 1]
            index += 2
        else:
            index += 1
    return parsed


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def main() -> int:
    args = parse_args(sys.argv[1:])

    with open(os.environ["AGY_STUB_CALLS"], "a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "prompt": args.get("prompt", ""),
                    "add_dir": args.get("add_dir", ""),
                    "effort": args.get("effort", ""),
                    "timeout": args.get("print_timeout", ""),
                    "cwd": os.getcwd(),
                    "author_date": os.environ.get("GIT_AUTHOR_DATE", ""),
                    "committer_date": os.environ.get("GIT_COMMITTER_DATE", ""),
                }
            )
            + "\n"
        )

    mode = os.environ.get("AGY_STUB_MODE", "all")

    if mode == "first":
        # This very call is already recorded, so >1 means a later call.
        with open(os.environ["AGY_STUB_CALLS"], encoding="utf-8") as handle:
            calls = sum(1 for line in handle if line.strip())
        if calls > 1:
            print("stub: refusing to commit any further units")
            return 0
        mode = "one"

    if mode == "none":
        print("a tool required the command permission, but headless mode cannot prompt")
        log_file = args.get("log_file")
        if log_file:
            Path(log_file).write_text(
                'permission check failed for command "git ls-files --others"\n',
                encoding="utf-8",
            )
        return 0

    if mode == "auth":
        # Names both causes on purpose: auth is the more specific one and has to
        # win over the timeout recognizer.
        print("authentication failed or timed out")
        return 0

    if mode == "quota":
        print("RESOURCE_EXHAUSTED: usage limit reached, token budget spent")
        return 0

    if mode == "timeout":
        print("deadline exceeded while generating the commit")
        return 0

    pending = [line[3:] for line in git("status", "--porcelain").splitlines()]
    if mode == "one":
        pending = pending[:1]
    if not pending:
        return 0

    for path in pending:
        git("add", path)
    git("commit", "-q", "-m", "stub: " + " ".join(pending))
    return 0


if __name__ == "__main__":
    sys.exit(main())
