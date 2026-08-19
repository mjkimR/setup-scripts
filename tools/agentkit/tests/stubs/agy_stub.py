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

Polish-prompt modes, driven by the target list in the prompt:

    polish          edit every target and mark each POLISHED
    polish-clean    edit nothing, mark every target CLEAN
    polish-partial  edit and mark the first target, stay silent on the rest
    polish-liar     edit nothing but mark every target POLISHED
    polish-delete   delete every target and mark each POLISHED
    polish-wrong-style  edit and mark every target, but acknowledge another 어체
    polish-no-style     edit and mark every target, but skip the STYLE line
"""

import json
import os
import re
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
        elif token == "--add-dir":
            # Repeatable: keep the first (the workdir) where old tests look,
            # and the full list for the polish tests.
            parsed.setdefault("add_dir", argv[index + 1])
            parsed.setdefault("add_dirs", []).append(argv[index + 1])
            index += 2
        elif token.startswith("--"):
            parsed[token[2:].replace("-", "_")] = argv[index + 1]
            index += 2
        else:
            index += 1
    return parsed


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def run_polish_mode(mode: str, prompt: str) -> int:
    """Behave like a polish receiver: the prompt's target list drives the run."""
    targets = re.findall(r"^- (?:changed-regions|whole-file) :: (.+)$", prompt, re.MULTILINE)
    for index, target in enumerate(targets):
        path = Path(target) if Path(target).is_absolute() else Path.cwd() / target
        if mode in ("polish", "polish-wrong-style", "polish-no-style") or (mode == "polish-partial" and index == 0):
            path.write_text(path.read_text(encoding="utf-8") + "\npolished\n", encoding="utf-8")
            print(f"POLISHED: {target}")
        elif mode == "polish-clean":
            print(f"CLEAN: {target}")
        elif mode == "polish-liar":
            print(f"POLISHED: {target}")
        elif mode == "polish-delete":
            path.unlink()
            print(f"POLISHED: {target}")

    # A cooperative receiver echoes back the 어체 each target was handed. The
    # prompt groups targets under a `[L2 해라체 (평서형)]` heading per pack.
    if mode != "polish-no-style":
        for target, level in style_groups(prompt).items():
            if mode == "polish-wrong-style":
                level = "L1" if level != "L1" else "L5"
            print(f"STYLE: {target} {level}")
    return 0


def style_groups(prompt: str) -> dict:
    """Map each target in the prompt to the level of the group it sits under."""
    assigned, level = {}, None
    for line in prompt.splitlines():
        heading = re.match(r"^\[(L\d) ", line)
        if heading:
            level = heading.group(1)
            continue
        target = re.match(r"^- (?:changed-regions|whole-file) :: (.+)$", line)
        if target and level:
            assigned[target.group(1)] = level
    return assigned


def write_completion_report(prompt: str) -> None:
    """Cooperative modes honour a work prompt's completion-report instruction."""
    match = re.search(r"completion report to (\S+)", prompt)
    if match:
        Path(match.group(1)).write_text("stub completion report\n", encoding="utf-8")


def main() -> int:
    args = parse_args(sys.argv[1:])

    with open(os.environ["AGY_STUB_CALLS"], "a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "prompt": args.get("prompt", ""),
                    "add_dir": args.get("add_dir", ""),
                    "add_dirs": args.get("add_dirs", []),
                    "mode_flag": args.get("mode", ""),
                    "effort": args.get("effort", ""),
                    "model": args.get("model", ""),
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
            # Overridable so tests can deny a command outside the task's
            # permitted set, not just an in-scope one missing its grant.
            denied = os.environ.get("AGY_STUB_DENIED", "git ls-files --others")
            Path(log_file).write_text(
                f'permission check failed for command "{denied}"\n',
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

    if mode.startswith("polish"):
        return run_polish_mode(mode, args.get("prompt", ""))

    write_completion_report(args.get("prompt", ""))

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
