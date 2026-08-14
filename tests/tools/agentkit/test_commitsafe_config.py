"""The commit-safe config reader and the whitelist it feeds."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agentkit.commitsafe import checked_identity, load_config, write_default_config
from agentkit.commitsafe import config as safe_config
from agentkit.errors import ConfigError, ExitCode, IdentityError


def test_missing_config_reports_exit_code_two(monkeypatch, tmp_path):
    monkeypatch.setenv(safe_config.CONFIG_ENV, str(tmp_path / "absent.yaml"))

    with pytest.raises(ConfigError) as caught:
        load_config()

    # Skills branch on this: 2 is "nothing is set up", 1 is "you may not commit".
    assert caught.value.exit_code == ExitCode.INCOMPLETE


def test_reads_every_field(monkeypatch, tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
allowed_emails:
  - one@example.com
  - two@example.com   # trailing comment

time:
  range:
    start: "08:30"
    end: "09:45"
  timezone: "UTC"
  min_gap_seconds: 90
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.setenv(safe_config.CONFIG_ENV, str(path))

    config = load_config()

    assert config.allowed_emails == ["one@example.com", "two@example.com"]
    assert (config.start, config.end) == ("08:30", "09:45")
    assert config.timezone == "UTC"
    assert config.min_gap_seconds == 90


def test_defaults_fill_in_what_the_file_omits(monkeypatch, tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text("allowed_emails:\n  - one@example.com\n", encoding="utf-8")
    monkeypatch.setenv(safe_config.CONFIG_ENV, str(path))

    config = load_config()

    assert config.timezone == safe_config.DEFAULT_TIMEZONE
    assert config.min_gap_seconds == safe_config.DEFAULT_MIN_GAP_SECONDS


def test_an_empty_whitelist_is_a_config_error(monkeypatch, tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text("time:\n  timezone: UTC\n", encoding="utf-8")
    monkeypatch.setenv(safe_config.CONFIG_ENV, str(path))

    with pytest.raises(ConfigError):
        load_config()


def test_generated_config_loads_back(monkeypatch, tmp_path: Path):
    path = tmp_path / "nested" / "config.yaml"
    write_default_config(path, "seeded@example.com")
    monkeypatch.setenv(safe_config.CONFIG_ENV, str(path))

    assert load_config().allowed_emails == ["seeded@example.com"]


def test_whitelisted_identity_passes(safe_setup, repo: Path):
    config, email = checked_identity()

    assert email == "test@example.com"
    assert config.allows(email)


def test_foreign_identity_is_rejected(safe_setup, repo: Path):
    subprocess.run(
        ["git", "config", "user.email", "stranger@example.com"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )

    with pytest.raises(IdentityError) as caught:
        checked_identity()

    assert caught.value.exit_code == ExitCode.FAILED
    assert "stranger@example.com" in str(caught.value)
