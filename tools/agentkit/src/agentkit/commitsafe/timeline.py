"""Commit timestamp resolution within configured daily time windows."""

from __future__ import annotations

import json
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime, tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo

from ..repoconfig import load_repo_config
from .config import Config, load_config

STATE_ENV = "XDG_STATE_HOME"
DEFAULT_STATE_HOME = Path.home() / ".local" / "state"


@dataclass
class Stamp:
    when: datetime
    first_of_day: bool
    enabled: bool = True

    def format(self) -> str:
        if not self.enabled:
            return f"{self.when.strftime('%Y-%m-%d %H:%M:%S %z')} (system clock / timeline disabled)"
        return self.when.strftime("%Y-%m-%d %H:%M:%S %z")

    def as_env(self) -> dict:
        if not self.enabled:
            return {}
        stamp = self.when.strftime("%Y-%m-%d %H:%M:%S %z")
        return {"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}


def state_path() -> Path:
    home = os.environ.get(STATE_ENV)
    base = Path(home).expanduser() if home else DEFAULT_STATE_HOME
    return base / "git-commit-safe" / "state.json"


def resolve(
    config: Config | None = None,
    *,
    persist: bool = True,
    cwd: Path | None = None,
) -> Stamp:
    """Resolve the timestamp for the next commit.

    `persist=False` previews the result without consuming it, which is what
    `verify` needs — checking should never advance the day's sequence.
    """
    repo_cfg = load_repo_config(cwd=cwd)
    if repo_cfg is not None:
        if not repo_cfg.timeline.enabled:
            tz = _timezone(repo_cfg.timeline.timezone)
            return Stamp(when=datetime.now(tz), first_of_day=False, enabled=False)
        config = Config(
            path=repo_cfg.path,
            allowed_emails=repo_cfg.whitelist.allowed_emails,
            timezone=repo_cfg.timeline.timezone,
            start=repo_cfg.timeline.start,
            end=repo_cfg.timeline.end,
            min_gap_seconds=repo_cfg.timeline.min_gap_seconds,
        )
    elif config is None:
        config = load_config()

    tz = _timezone(config.timezone)
    now = datetime.now(tz)
    today = now.strftime("%Y-%m-%d")
    now_epoch = time.time()

    state = _load_state()
    resumable = (
        state.get("date") == today
        and {
            "real_start_epoch",
            "virtual_start_epoch",
        }
        <= state.keys()
    )

    if resumable:
        elapsed = max(0.0, now_epoch - state["real_start_epoch"])
        target = state["virtual_start_epoch"] + elapsed

        # The floor is measured against the previous commit, not against zero:
        # two commits a few seconds apart would otherwise format to timestamps
        # that differ by less than min_gap_seconds, or to the very same second.
        last = state.get("last_virtual_epoch", state["virtual_start_epoch"])
        if target < last + config.min_gap_seconds:
            target = last + random.randint(config.min_gap_seconds, config.min_gap_seconds + 45)

        state["last_virtual_epoch"] = target
    else:
        target = _random_start(config, now, tz)
        state = {
            "date": today,
            "real_start_epoch": now_epoch,
            "virtual_start_epoch": target,
            "last_virtual_epoch": target,
        }

    if persist:
        _save_state(state)

    return Stamp(when=datetime.fromtimestamp(target, tz), first_of_day=not resumable)


def _random_start(config: Config, now: datetime, tz: tzinfo) -> float:
    start_hour, start_minute = _hhmm(config.start)
    end_hour, end_minute = _hhmm(config.end)

    start = datetime(now.year, now.month, now.day, start_hour, start_minute, tzinfo=tz)
    end = datetime(now.year, now.month, now.day, end_hour, end_minute, tzinfo=tz)

    epoch_start = start.timestamp()
    epoch_end = end.timestamp()
    # A window that ends before it starts is a config typo, not a wrap-around.
    if epoch_end <= epoch_start:
        epoch_end = epoch_start + 3600

    return random.uniform(epoch_start, epoch_end)


def _hhmm(value: str) -> tuple[int, int]:
    hour, minute = value.split(":")
    return int(hour), int(minute)


def _timezone(name: str) -> tzinfo:
    try:
        return ZoneInfo(name)
    except Exception:
        local: tzinfo | None = datetime.now().astimezone().tzinfo
        assert local is not None
        return local


def _load_state() -> dict:
    path = state_path()
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # A corrupt state file should start a fresh day, not block the commit.
        return {}


def _save_state(state: dict) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
