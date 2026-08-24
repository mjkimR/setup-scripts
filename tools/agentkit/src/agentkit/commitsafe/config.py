"""Global commit-safe configuration loader and writer."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..errors import ConfigError

CONFIG_ENV = "AGENTKIT_COMMIT_SAFE_CONFIG"
DEFAULT_CONFIG_PATH = Path.home() / ".config" / "git-commit-safe" / "config.yaml"

DEFAULT_TIMEZONE = "Asia/Seoul"
DEFAULT_START = "09:00"
DEFAULT_END = "18:00"
DEFAULT_MIN_GAP_SECONDS = 30


@dataclass
class Config:
    path: Path
    allowed_emails: list[str] = field(default_factory=list)
    timezone: str = DEFAULT_TIMEZONE
    start: str = DEFAULT_START
    end: str = DEFAULT_END
    min_gap_seconds: int = DEFAULT_MIN_GAP_SECONDS
    whitelist_enabled: bool = True

    def allows(self, email: str) -> bool:
        if not self.whitelist_enabled:
            return True
        return email in self.allowed_emails


def config_path() -> Path:
    override = os.environ.get(CONFIG_ENV)
    return Path(override).expanduser() if override else DEFAULT_CONFIG_PATH


def load_config() -> Config:
    path = config_path()
    if not path.is_file():
        raise ConfigError(
            f"commit-safe config not found at: {path}",
            fix="agentkit commit-safe init",
            what_to_report="commit-safe configuration file is missing. Proceed with creating one?",
            details=["Run `agentkit commit-safe init` to create one."],
        )

    text = path.read_text(encoding="utf-8")
    config = Config(path=path, allowed_emails=_emails(text))

    for attribute, key, pattern in (
        ("timezone", "timezone", r"[^\"'\s\n]+"),
        ("start", "start", r"[0-9]{1,2}:[0-9]{2}"),
        ("end", "end", r"[0-9]{1,2}:[0-9]{2}"),
    ):
        value = _scalar(text, key, pattern)
        if value:
            setattr(config, attribute, value)

    gap = _scalar(text, "min_gap_seconds", r"[0-9]+")
    if gap:
        config.min_gap_seconds = int(gap)

    if not config.allowed_emails:
        raise ConfigError(
            f"no allowed_emails listed in: {path}",
            fix="agentkit commit-safe init --force",
            what_to_report="No allowed emails found in commit-safe configuration.",
            details=["Add at least one address, or re-run `agentkit commit-safe init --force`."],
        )

    return config


def write_default_config(path: Path, email: str) -> None:
    """Write a starter config seeded with the caller's current git identity."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""# {path}

allowed_emails:
  - {email}

time:
  # Daily working-hours window (HH:MM ~ HH:MM). Commits made inside it keep the
  # real clock; a session outside it opens within 30 minutes of `start`.
  range:
    start: "{DEFAULT_START}"
    end: "{DEFAULT_END}"

  timezone: "{DEFAULT_TIMEZONE}"

  # Minimum gap in seconds between consecutive commits
  min_gap_seconds: {DEFAULT_MIN_GAP_SECONDS}
""",
        encoding="utf-8",
    )


def _emails(text: str) -> list[str]:
    block = re.search(r"allowed_emails:\s*\n((?:\s*-\s*[^\n]+\n?)+)", text)
    if not block:
        return []
    return [item.strip() for item in re.findall(r"-\s*([^\s#]+)", block.group(1))]


def _scalar(text: str, key: str, value_pattern: str) -> str:
    match = re.search(rf"{key}:\s*[\"']?({value_pattern})[\"']?", text)
    return match.group(1).strip() if match else ""
