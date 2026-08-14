"""Per-repository commit configuration and history analysis.

Stored per-repository at `<git-dir>/agentkit-commit.json`.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from . import gitutil
from .errors import ConfigError

DEFAULT_TIMEZONE = "Asia/Seoul"
DEFAULT_START = "19:00"
DEFAULT_END = "21:00"
DEFAULT_MIN_GAP_SECONDS = 30


@dataclass
class WhitelistConfig:
    enabled: bool = True
    allowed_emails: list[str] = field(default_factory=list)

    def allows(self, email: str) -> bool:
        if not self.enabled:
            return True
        return email in self.allowed_emails


@dataclass
class TimelineConfig:
    enabled: bool = True
    timezone: str = DEFAULT_TIMEZONE
    start: str = DEFAULT_START
    end: str = DEFAULT_END
    min_gap_seconds: int = DEFAULT_MIN_GAP_SECONDS


@dataclass
class ConventionConfig:
    language: str = "ko"  # "ko" or "en"
    style: str = "conventional"  # "conventional", "bracketed", "ticket", "freeform"
    template: str = "<type>(<scope>): <subject>\n\n<summary>\n- <bullet point 1>\n- <bullet point 2>"
    rules: list[str] = field(default_factory=list)


CURRENT_CONFIG_VERSION = 1


@dataclass
class RepoConfig:
    path: Path
    version: int = CURRENT_CONFIG_VERSION
    whitelist: WhitelistConfig = field(default_factory=WhitelistConfig)
    timeline: TimelineConfig = field(default_factory=TimelineConfig)
    conventions: ConventionConfig = field(default_factory=ConventionConfig)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("path", None)
        return data

    @classmethod
    def from_dict(cls, path: Path, data: dict[str, Any]) -> RepoConfig:
        whitelist_data = data.get("whitelist", {}) if isinstance(data.get("whitelist"), dict) else {}
        timeline_data = data.get("timeline", {}) if isinstance(data.get("timeline"), dict) else {}
        conventions_data = data.get("conventions", {}) if isinstance(data.get("conventions"), dict) else {}

        return cls(
            path=path,
            version=data.get("version", CURRENT_CONFIG_VERSION),
            whitelist=WhitelistConfig(
                enabled=whitelist_data.get("enabled", True),
                allowed_emails=list(whitelist_data.get("allowed_emails", [])),
            ),
            timeline=TimelineConfig(
                enabled=timeline_data.get("enabled", True),
                timezone=timeline_data.get("timezone", DEFAULT_TIMEZONE),
                start=timeline_data.get("start", DEFAULT_START),
                end=timeline_data.get("end", DEFAULT_END),
                min_gap_seconds=timeline_data.get("min_gap_seconds", DEFAULT_MIN_GAP_SECONDS),
            ),
            conventions=ConventionConfig(
                language=conventions_data.get("language", "ko"),
                style=conventions_data.get("style", "conventional"),
                template=conventions_data.get(
                    "template",
                    "<type>(<scope>): <subject>\n\n<summary>\n- <bullet point 1>\n- <bullet point 2>",
                ),
                rules=list(conventions_data.get("rules", [])),
            ),
        )


def needs_migration(config: RepoConfig) -> bool:
    return config.version < CURRENT_CONFIG_VERSION


def migrate_config(config: RepoConfig) -> RepoConfig:
    config.version = CURRENT_CONFIG_VERSION
    return config


def git_dir(cwd: Path | None = None) -> Path:
    """Find the .git directory (or gitdir for worktrees) of the current repository."""
    raw = gitutil.run(["rev-parse", "--git-dir"], cwd=cwd).strip()
    path = Path(raw)
    if not path.is_absolute():
        root = gitutil.repo_root(cwd=cwd)
        path = (root / path).resolve()
    return path


def repo_config_path(cwd: Path | None = None) -> Path:
    return git_dir(cwd=cwd) / "agentkit-commit.json"


def load_repo_config(cwd: Path | None = None, *, auto_migrate: bool = False) -> RepoConfig | None:
    try:
        path = repo_config_path(cwd=cwd)
    except Exception:
        return None

    if not path.is_file():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        cfg = RepoConfig.from_dict(path, data)
        if auto_migrate and needs_migration(cfg):
            migrate_config(cfg)
            save_repo_config(cfg, cwd=cwd)
        return cfg
    except (json.JSONDecodeError, OSError) as error:
        raise ConfigError(
            f"failed to read repository commit config at {path}: {error}",
            "Fix the JSON syntax or re-run onboarding.",
        ) from error


def save_repo_config(config: RepoConfig, cwd: Path | None = None) -> Path:
    path = repo_config_path(cwd=cwd)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = config.to_dict()
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def analyze_repo_history(cwd: Path | None = None, count: int = 25) -> dict[str, Any]:
    """Inspect recent git commit history to infer author, language, style, and template."""
    root = gitutil.repo_root(cwd=cwd)
    head = gitutil.head_sha(cwd=root)

    current_email = gitutil.config_value("user.email", cwd=root)

    if not head:
        # Empty repository fallback
        return {
            "emails": [current_email] if current_email else [],
            "primary_email": current_email or "user@example.com",
            "language": "ko",
            "style": "conventional",
            "sample_subjects": [],
            "suggested_template": "<type>(<scope>): <subject>\n\n[선택] 변경 목적 및 배경 1-2줄\n\n- <주요 변경 사항 1>\n- <주요 변경 사항 2>",
            "total_commits": 0,
        }

    # Format: hash | author_name | author_email | subject
    raw_lines = gitutil.run(
        ["log", f"-n {count}", "--format=%h%x09%an%x09%ae%x09%s"],
        cwd=root,
    ).splitlines()

    emails: list[str] = []
    subjects: list[str] = []

    for line in raw_lines:
        parts = line.split("\t")
        if len(parts) >= 4:
            emails.append(parts[2].strip())
            subjects.append(parts[3].strip())
        elif len(parts) == 1 and parts[0]:
            subjects.append(parts[0].strip())

    email_counter = Counter(emails)
    ranked_emails = [email for email, _ in email_counter.most_common()]
    if current_email and current_email not in ranked_emails:
        ranked_emails.insert(0, current_email)
    primary_email = current_email or (ranked_emails[0] if ranked_emails else "user@example.com")

    # Detect language: check for Hangul characters in commit subjects
    hangul_pattern = re.compile(r"[\uac00-\ud7a3\u1100-\u11ff\u3130-\u318f]")
    hangul_count = sum(1 for s in subjects if hangul_pattern.search(s))
    total_subjects = len(subjects) or 1
    language = "ko" if (hangul_count / total_subjects) >= 0.25 else "en"

    # Detect style:
    conventional_re = re.compile(
        r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([^\)]+\))?!?:",
        re.IGNORECASE,
    )
    bracketed_re = re.compile(r"^\[[^\]]+\]")
    ticket_re = re.compile(r"^[A-Z]+-[0-9]+", re.IGNORECASE)

    conventional_count = sum(1 for s in subjects if conventional_re.match(s))
    bracketed_count = sum(1 for s in subjects if bracketed_re.match(s))
    ticket_count = sum(1 for s in subjects if ticket_re.match(s))

    if bracketed_count >= conventional_count and bracketed_count > 0:
        style = "bracketed"
        if language == "ko":
            template = "[<모듈/범위>] <작업 내용 요약>\n\n[선택] 변경 배경 및 상세 설명\n\n- <상세 변경 사항 1>\n- <상세 변경 사항 2>"
        else:
            template = (
                "[<scope>] <subject line>\n\n[Optional] High-level intent summary\n\n- <Key change 1>\n- <Key change 2>"
            )
    elif ticket_count >= conventional_count and ticket_count > 0:
        style = "ticket"
        if language == "ko":
            template = "[<TICKET-ID>] <type>: <작업 내용 요약>\n\n[선택] 변경 배경 및 상세 설명\n\n- <상세 변경 사항 1>\n- <상세 변경 사항 2>"
        else:
            template = "[<TICKET-ID>] <type>: <subject line>\n\n[Optional] High-level intent summary\n\n- <Key change 1>\n- <Key change 2>"
    else:
        style = "conventional"
        if language == "ko":
            template = "<type>(<scope>): <간결한 커밋 요약>\n\n[선택] 변경 배경 및 목적 1-2줄\n\n- <주요 변경 사항 1>\n- <주요 변경 사항 2>"
        else:
            template = "<type>(<scope>): <short subject line>\n\n[Optional] Overview of intent or motivation\n\n- <Key change 1>\n- <Key change 2>"

    return {
        "emails": ranked_emails,
        "primary_email": primary_email,
        "language": language,
        "style": style,
        "sample_subjects": subjects[:5],
        "suggested_template": template,
        "total_commits": len(subjects),
    }
