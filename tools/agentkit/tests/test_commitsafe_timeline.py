"""Timestamp progression: the window, the elapsed-time carry, the minimum gap."""

from __future__ import annotations

import json
from datetime import datetime
from itertools import pairwise

from agentkit.commitsafe import load_config, resolve, state_path


def test_first_of_the_day_lands_inside_the_window(safe_setup):
    config = load_config()

    stamp = resolve(config)

    assert stamp.first_of_day
    assert datetime.strptime("19:00", "%H:%M").time() <= stamp.when.time()
    assert stamp.when.time() <= datetime.strptime("21:00", "%H:%M").time()


def test_state_is_written_once_consumed(safe_setup):
    config = load_config()
    resolve(config)

    state = json.loads(state_path(config).read_text(encoding="utf-8"))
    assert set(state) == {
        "date",
        "real_start_epoch",
        "virtual_start_epoch",
        "last_virtual_epoch",
    }


def test_a_preview_neither_advances_nor_persists(safe_setup):
    config = load_config()

    preview = resolve(config, persist=False)

    assert not state_path(config).exists()
    assert resolve(config, persist=False).first_of_day
    assert preview.first_of_day


def test_back_to_back_commits_keep_the_minimum_gap(safe_setup):
    config = load_config()

    stamps = [resolve(config) for _ in range(4)]

    seconds = [stamp.when.timestamp() for stamp in stamps]
    gaps = [later - earlier for earlier, later in pairwise(seconds)]
    # Without the floor these calls land in the same second: the elapsed real
    # time between them is milliseconds.
    assert all(gap >= config.min_gap_seconds for gap in gaps), gaps
    assert stamps[0].first_of_day
    assert not any(stamp.first_of_day for stamp in stamps[1:])


def test_a_corrupt_state_file_starts_a_fresh_day(safe_setup):
    config = load_config()
    path = state_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not json", encoding="utf-8")

    assert resolve(config).first_of_day


def test_a_stale_state_file_starts_a_fresh_day(safe_setup):
    config = load_config()
    resolve(config)

    path = state_path(config)
    state = json.loads(path.read_text(encoding="utf-8"))
    state["date"] = "1999-01-01"
    path.write_text(json.dumps(state), encoding="utf-8")

    assert resolve(config).first_of_day


def test_configs_do_not_share_a_timeline(safe_setup, tmp_path):
    """A second repo the same day must start its own window, not inherit one."""
    from agentkit.commitsafe.config import Config

    first = load_config()
    second = Config(
        path=tmp_path / "other-repo" / "agentkit-commit.json",
        allowed_emails=first.allowed_emails,
        timezone=first.timezone,
        start=first.start,
        end=first.end,
        min_gap_seconds=first.min_gap_seconds,
    )

    resolve(first)

    assert state_path(first) != state_path(second)
    assert resolve(second).first_of_day
