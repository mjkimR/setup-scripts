"""Commit timestamp resolution within configured daily time windows."""

from __future__ import annotations

import hashlib
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

# Real elapsed time is carried into the virtual timeline commit by commit, but
# only while it stays plausible as one edit-and-commit cycle. Carrying it
# verbatim was the convenient thing, not the right one: an hour of thinking
# between two commits dragged the day's later stamps far outside the window.
# Past the threshold the advance collapses to a gap that still reads as work.
CARRY_THRESHOLD_SECONDS = 120
CLAMPED_GAP_SECONDS = (60, 120)

# How far past the window's opening the day's first commit may be dropped when
# the real clock sits outside working hours. Spreading it across the whole
# window instead would put the day's first commit at an arbitrary afternoon
# hour and every later one after it.
FIRST_COMMIT_JITTER_SECONDS = 30 * 60


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


def state_path(config: Config | None = None) -> Path:
    """State file for one config — repos must not share a virtual timeline.

    Keyed by the config's path: a repo config gets its own file, while every
    caller of the one global config still shares a single timeline.
    """
    home = os.environ.get(STATE_ENV)
    base = Path(home).expanduser() if home else DEFAULT_STATE_HOME
    directory = base / "git-commit-safe"
    if config is None:
        return directory / "state.json"
    digest = hashlib.sha256(str(config.path).encode("utf-8")).hexdigest()[:12]
    return directory / f"state-{digest}.json"


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
    now = _now(tz)
    today = now.strftime("%Y-%m-%d")
    now_epoch = time.time()

    state = _load_state(config)
    resumable = (
        state.get("date") == today
        and {
            "real_start_epoch",
            "virtual_start_epoch",
        }
        <= state.keys()
    )

    if resumable:
        # Both fall back to the day's anchor so a state file written before
        # last_real_epoch existed still resumes instead of restarting the day.
        last_real = state.get("last_real_epoch", state["real_start_epoch"])
        last_virtual = state.get("last_virtual_epoch", state["virtual_start_epoch"])

        real_gap = max(0.0, now_epoch - last_real)
        advance = real_gap if real_gap < CARRY_THRESHOLD_SECONDS else random.uniform(*CLAMPED_GAP_SECONDS)
        target = last_virtual + advance

        # The floor is measured against the previous commit, not against zero:
        # two commits a few seconds apart would otherwise format to timestamps
        # that differ by less than min_gap_seconds, or to the very same second.
        if target < last_virtual + config.min_gap_seconds:
            target = last_virtual + random.randint(config.min_gap_seconds, config.min_gap_seconds + 45)

        state["last_virtual_epoch"] = target
        state["last_real_epoch"] = now_epoch
    else:
        target = _day_start(config, now, tz)
        state = {
            "date": today,
            "real_start_epoch": now_epoch,
            "virtual_start_epoch": target,
            "last_virtual_epoch": target,
            "last_real_epoch": now_epoch,
        }

    if persist:
        _save_state(state, config)

    return Stamp(when=datetime.fromtimestamp(target, tz), first_of_day=not resumable)


def _day_start(config: Config, now: datetime, tz: tzinfo) -> float:
    """Where the day's first commit lands on the virtual timeline.

    Inside the window the real clock already reads as work, so it is kept as
    is. Outside it — a pre-dawn session, or one running well past the evening
    — the day opens shortly after `start` instead.
    """
    start_hour, start_minute = _hhmm(config.start)
    end_hour, end_minute = _hhmm(config.end)

    start = datetime(now.year, now.month, now.day, start_hour, start_minute, tzinfo=tz)
    end = datetime(now.year, now.month, now.day, end_hour, end_minute, tzinfo=tz)

    epoch_start = start.timestamp()
    epoch_end = end.timestamp()
    # A window that ends before it starts is a config typo, not a wrap-around.
    if epoch_end <= epoch_start:
        epoch_end = epoch_start + 3600

    epoch_now = now.timestamp()
    if epoch_start <= epoch_now <= epoch_end:
        return epoch_now

    # A window narrower than the jitter must still contain its own first commit.
    jitter = min(FIRST_COMMIT_JITTER_SECONDS, epoch_end - epoch_start)
    return random.uniform(epoch_start, epoch_start + jitter)


def _hhmm(value: str) -> tuple[int, int]:
    hour, minute = value.split(":")
    return int(hour), int(minute)


def _now(tz: tzinfo) -> datetime:
    """The wall clock, as one seam the tests can hold still."""
    return datetime.now(tz)


def _timezone(name: str) -> tzinfo:
    try:
        return ZoneInfo(name)
    except Exception:
        local: tzinfo | None = datetime.now().astimezone().tzinfo
        assert local is not None
        return local


def _load_state(config: Config) -> dict:
    path = state_path(config)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # A corrupt state file should start a fresh day, not block the commit.
        return {}


def _save_state(state: dict, config: Config) -> None:
    path = state_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
