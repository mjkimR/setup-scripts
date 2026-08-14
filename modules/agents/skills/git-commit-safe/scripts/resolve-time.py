#!/usr/bin/env python3
"""
git-commit-safe time resolution and email validation engine.
Calculates realistic commit timestamps:
- 1st commit of the day: Random time within configured range (e.g. 19:00 ~ 21:00).
- Subsequent commits: Progresses naturally by adding elapsed real time since the 1st commit.
- Rapid commits: Enforces strict monotonic increment (+30s..+90s) to avoid timestamp collision.
"""

import os
import sys
import json
import re
import time
import random
from datetime import datetime, date
try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None


def parse_simple_yaml(filepath):
    """Parses basic YAML structure (allowed_emails list and time dict) without third-party dependencies."""
    if not os.path.isfile(filepath):
        return None

    config = {
        "allowed_emails": [],
        "time": {
            "range": {"start": "19:00", "end": "21:00"},
            "timezone": "Asia/Seoul",
            "min_gap_seconds": 30
        }
    }

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Extract allowed_emails
    emails_block = re.search(r"allowed_emails:\s*\n((?:\s*-\s*[^\n]+\n?)+)", content)
    if emails_block:
        emails = re.findall(r"-\s*([^\s#]+)", emails_block.group(1))
        config["allowed_emails"] = [e.strip() for e in emails if e.strip()]

    # Extract timezone
    tz_match = re.search(r"timezone:\s*[\"']?([^\"'\s\n]+)[\"']?", content)
    if tz_match:
        config["time"]["timezone"] = tz_match.group(1).strip()

    # Extract range start and end
    start_match = re.search(r"start:\s*[\"']?([0-9]{1,2}:[0-9]{2})[\"']?", content)
    if start_match:
        config["time"]["range"]["start"] = start_match.group(1).strip()

    end_match = re.search(r"end:\s*[\"']?([0-9]{1,2}:[0-9]{2})[\"']?", content)
    if end_match:
        config["time"]["range"]["end"] = end_match.group(1).strip()

    # Extract min_gap_seconds
    gap_match = re.search(r"min_gap_seconds:\s*([0-9]+)", content)
    if gap_match:
        config["time"]["min_gap_seconds"] = int(gap_match.group(1))

    return config


def get_current_git_email():
    import subprocess
    try:
        res = subprocess.run(["git", "config", "user.email"], capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except Exception:
        return ""


def get_tz(tz_name):
    if ZoneInfo:
        try:
            return ZoneInfo(tz_name)
        except Exception:
            pass
    return datetime.now().astimezone().tzinfo


def resolve():
    config_file = os.environ.get("SAFE_COMMIT_CONFIG", os.path.expanduser("~/.config/git-commit-safe/config.yaml"))
    state_dir = os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state"))
    state_file = os.path.join(state_dir, "git-commit-safe", "state.json")

    # 1. Config file check
    if not os.path.isfile(config_file):
        sys.stderr.write(f"[ERROR] git-commit-safe config file not found at: {config_file}\n")
        sys.stderr.write("[INFO] Please refer to the onboarding guide: references/onboard.md\n")
        sys.stderr.write("[INFO] Or run: scripts/setup-config.sh\n")
        sys.exit(2)

    config = parse_simple_yaml(config_file)
    if not config:
        sys.stderr.write(f"[ERROR] Failed to parse config file: {config_file}\n")
        sys.exit(2)

    # 2. Email verification
    current_email = get_current_git_email()
    if not current_email:
        sys.stderr.write("[ERROR] No git email configured ('git config user.email' is empty).\n")
        sys.stderr.write("[INFO] Configure your email: git config user.email \"your@email.com\"\n")
        sys.exit(1)

    if current_email not in config["allowed_emails"]:
        sys.stderr.write("[ERROR] Email verification failed!\n")
        sys.stderr.write(f"[ERROR] Current git email '{current_email}' is NOT in whitelist: {config_file}\n")
        sys.stderr.write(f"[INFO] Allowed emails: {', '.join(config['allowed_emails'])}\n")
        sys.exit(1)

    # 3. Time calculation
    tz = get_tz(config["time"]["timezone"])
    now = datetime.now(tz)
    today_str = now.strftime("%Y-%m-%d")
    now_epoch = time.time()

    # Load state
    state = {}
    if os.path.isfile(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            state = {}

    is_first_commit_today = False
    min_gap = config["time"]["min_gap_seconds"]

    if state.get("date") == today_str and "real_start_epoch" in state and "virtual_start_epoch" in state:
        # Subsequent commit of the day
        real_start = state["real_start_epoch"]
        virtual_start = state["virtual_start_epoch"]
        last_virtual = state.get("last_virtual_epoch", virtual_start)

        elapsed_real = max(0.0, now_epoch - real_start)
        target_virtual = virtual_start + elapsed_real

        # Ensure strict forward progress
        if target_virtual <= last_virtual:
            target_virtual = last_virtual + random.randint(min_gap, min_gap + 45)

        state["last_virtual_epoch"] = target_virtual
    else:
        # 1st commit of the day
        is_first_commit_today = True
        start_str = config["time"]["range"]["start"]
        end_str = config["time"]["range"]["end"]

        s_h, s_m = [int(x) for x in start_str.split(":")]
        e_h, e_m = [int(x) for x in end_str.split(":")]

        dt_start = datetime(now.year, now.month, now.day, s_h, s_m, 0, tzinfo=tz)
        dt_end = datetime(now.year, now.month, now.day, e_h, e_m, 0, tzinfo=tz)

        epoch_start = dt_start.timestamp()
        epoch_end = dt_end.timestamp()

        if epoch_end <= epoch_start:
            epoch_end = epoch_start + 3600

        # Random time within range
        virtual_start = random.uniform(epoch_start, epoch_end)
        target_virtual = virtual_start

        state = {
            "date": today_str,
            "real_start_epoch": now_epoch,
            "virtual_start_epoch": virtual_start,
            "last_virtual_epoch": virtual_start,
            "email": current_email
        }

    # Save state
    os.makedirs(os.path.dirname(state_file), exist_ok=True)
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

    # Format result timestamp
    dt_target = datetime.fromtimestamp(target_virtual, tz)
    formatted_date = dt_target.strftime("%Y-%m-%d %H:%M:%S %z")

    # Output
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "--env":
        print(f'export GIT_AUTHOR_DATE="{formatted_date}"')
        print(f'export GIT_COMMITTER_DATE="{formatted_date}"')
        print(f'export GIT_COMMIT_SAFE_EMAIL="{current_email}"')
    elif mode == "--stamp":
        # Bare timestamp, for callers that assign it directly instead of
        # eval-ing shell exports. Validation and state advance are identical.
        print(formatted_date)
    else:
        commit_type = "Today's 1st Commit (Random Base within Range)" if is_first_commit_today else "Today's Subsequent Commit (Accumulated Real Elapsed Time)"
        print("=== git-commit-safe Preflight Verification ===")
        print(f"✔ Config File:   {config_file}")
        print(f"✔ Git Email:     {current_email} (Whitelisted)")
        print(f"✔ Session Type:  {commit_type}")
        print(f"✔ Range Setting: {config['time']['range']['start']} ~ {config['time']['range']['end']} ({config['time']['timezone']})")
        print(f"✔ Resolved Time: {formatted_date}")
        print("✔ Status:        Passed")


if __name__ == "__main__":
    resolve()
