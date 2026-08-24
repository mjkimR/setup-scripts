"""Per-repository commit configuration and history analysis.

Stored per-repository at `<common-git-dir>/agentkit-commit.json`, with the
polish handoff's path→어체 map alongside it at `<common-git-dir>/agentkit-polish.json`.
The common git dir, not this checkout's: every worktree of a repository must
commit under the same whitelist, guards and conventions.
The two are separate files on purpose: the commit config is created by
onboarding and carries a schema version, while polishing works in any
repository, onboarded or not, and must not start demanding onboarding to
honor a level map.
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
DEFAULT_START = "09:00"
DEFAULT_END = "10:00"
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
    enabled: bool = False
    timezone: str = DEFAULT_TIMEZONE
    start: str = DEFAULT_START
    end: str = DEFAULT_END
    min_gap_seconds: int = DEFAULT_MIN_GAP_SECONDS


@dataclass
class ConventionConfig:
    language: str = "en"  # "ko" or "en"
    style: str = "conventional"  # "conventional", "bracketed", "ticket", "freeform"
    template: str = "<type>(<scope>): <subject>\n\n<summary>\n- <bullet point 1>\n- <bullet point 2>"
    rules: list[str] = field(default_factory=list)


# "bypass-intermediate": commits that leave further changes uncommitted use
# `git commit --no-verify`; the commit that empties the working tree runs
# hooks normally. "run-all" (keep every intermediate commit hook-green) is a
# reserved choice: recognized so the option space is visible, refused because
# nothing implements the grouping constraints it would impose.
HOOKS_POLICIES = ("bypass-intermediate", "run-all")
DEFAULT_HOOKS_POLICY = "bypass-intermediate"


@dataclass
class HooksConfig:
    policy: str = DEFAULT_HOOKS_POLICY


@dataclass
class GuardsConfig:
    """Pre-commit guardrails: where a commit may land, and what may go into it.

    Both path lists default to empty on purpose. A filename tells you almost
    nothing about whether a file holds a secret — `.env.example` is a normal
    file to commit — so the built-in check reads content, and the path lists
    exist only for the repository that knows something the scanner cannot.
    `allow_paths` exempts a path from the content scan, for the file whose job
    is to carry a credential-shaped string (a fixture, the scanner's own tests).
    """

    enabled: bool = True
    scan_secrets: bool = True
    protected_branches: list[str] = field(default_factory=list)
    deny_paths: list[str] = field(default_factory=list)
    allow_paths: list[str] = field(default_factory=list)

    def protects(self, branch: str) -> bool:
        return any(_glob_matches(pattern, branch) for pattern in self.protected_branches)

    def denies(self, display: str) -> bool:
        return any(_glob_matches(pattern, display) for pattern in self.deny_paths)

    def exempts(self, display: str) -> bool:
        return any(_glob_matches(pattern, display) for pattern in self.allow_paths)


@dataclass
class VerifyConfig:
    """Repo-provided verification commands; empty string means unconfigured.

    `enabled` exists apart from the commands so a repo mid-repair (tests
    known-broken and being fixed) can switch verification off without erasing
    the commands it will want back.
    """

    enabled: bool = True
    test: str = ""
    lint: str = ""

    def configured(self) -> list[tuple[str, str]]:
        return [(name, cmd) for name, cmd in (("test", self.test), ("lint", self.lint)) if cmd.strip()]

    def active(self) -> list[tuple[str, str]]:
        """The commands that should actually run: configured and not switched off."""
        return self.configured() if self.enabled else []


def ensure_supported_hooks_policy(policy: str) -> None:
    """Reject unknown policies and the recognized-but-closed `run-all`."""
    if policy not in HOOKS_POLICIES:
        raise ConfigError(
            f"unknown hooks.policy: {policy!r} (valid: {', '.join(HOOKS_POLICIES)}).",
            fix=f"agentkit commit config --set hooks.policy={DEFAULT_HOOKS_POLICY}",
            what_to_report="The repository's hooks.policy value is invalid; commits cannot proceed until it is fixed.",
        )
    if policy == "run-all":
        raise ConfigError(
            "hooks.policy=run-all is not implemented: keeping every intermediate commit hook-green "
            "is not supported yet.",
            fix=f"agentkit commit config --set hooks.policy={DEFAULT_HOOKS_POLICY}",
            what_to_report=(
                "hooks.policy=run-all was requested but is not implemented; the user must fall back to "
                "bypass-intermediate or wait for the feature."
            ),
            details=["The option is reserved on purpose — choosing it must fail loudly, not silently degrade."],
        )


POLISH_CONFIG_NAME = "agentkit-polish.json"


@dataclass(frozen=True)
class PolishConfig:
    """Path→어체 level map for `agentkit handoff polish`.

    Patterns are matched in file order and the first hit wins, so the specific
    ones go first. Last-match-wins was the alternative; first-match reads the
    way people write these lists — narrow rule at the top, catch-all below.
    """

    path: Path | None = None  # None when the repository has no map
    levels: dict[str, int] = field(default_factory=dict)

    def level_for(self, display: str) -> int | None:
        for pattern, level in self.levels.items():
            if _glob_matches(pattern, display):
                return level
        return None


def _glob_matches(pattern: str, display: str) -> bool:
    """gitignore-flavored matching: `**` crosses separators, `*` does not, and
    a pattern with no separator is matched against the basename."""
    subject = display if "/" in pattern else display.rsplit("/", 1)[-1]
    return re.fullmatch(_glob_to_regex(pattern), subject) is not None


def _glob_to_regex(pattern: str) -> str:
    out, index = [], 0
    while index < len(pattern):
        char = pattern[index]
        if pattern.startswith("**", index):
            out.append(".*")
            index += 2
        elif char == "*":
            out.append("[^/]*")
            index += 1
        elif char == "?":
            out.append("[^/]")
            index += 1
        else:
            out.append(re.escape(char))
            index += 1
    return "".join(out)


def polish_config_path(cwd: Path | None = None) -> Path:
    return common_git_dir(cwd=cwd) / POLISH_CONFIG_NAME


def load_polish_config(cwd: Path | None = None, *, valid_levels: tuple[int, ...] | None = None) -> PolishConfig:
    """Read the level map, or an empty one. Absent is normal; broken is not."""
    try:
        path = polish_config_path(cwd=cwd)
    except Exception:
        return PolishConfig()
    if not path.is_file():
        return PolishConfig()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        raise ConfigError(
            f"failed to read polish config at {path}: {error}",
            what_to_report="The repository's polish level map is unreadable; nothing was polished.",
            details=[f"Fix the JSON syntax in {path}, or delete the file to fall back to the default 어체."],
        ) from error

    raw = data.get("levels", {}) if isinstance(data, dict) else {}
    if not isinstance(raw, dict):
        raise ConfigError(
            f"polish config at {path} has a non-object 'levels'.",
            what_to_report="The repository's polish level map is malformed; nothing was polished.",
            details=['Expected {"levels": {"<glob>": <level>, …}}.'],
        )

    levels: dict[str, int] = {}
    for pattern, level in raw.items():
        # bool is an int subclass, and `true` here is a typo, not a level.
        if not isinstance(level, int) or isinstance(level, bool):
            raise ConfigError(
                f"polish config at {path} maps {pattern!r} to {level!r}, which is not a level.",
                what_to_report="The repository's polish level map has a non-numeric level; nothing was polished.",
                details=["Levels are integers; see `agentkit handoff polish --list-levels`."],
            )
        if valid_levels is not None and level not in valid_levels:
            raise ConfigError(
                f"polish config at {path} maps {pattern!r} to level {level}, which does not exist.",
                what_to_report=f"The repository's polish level map names level {level}; nothing was polished.",
                details=[f"Levels installed: {', '.join(str(item) for item in valid_levels)}."],
            )
        levels[pattern] = level
    return PolishConfig(path=path, levels=levels)


CURRENT_CONFIG_VERSION = 1


@dataclass
class RepoConfig:
    path: Path
    version: int = CURRENT_CONFIG_VERSION
    whitelist: WhitelistConfig = field(default_factory=WhitelistConfig)
    timeline: TimelineConfig = field(default_factory=TimelineConfig)
    conventions: ConventionConfig = field(default_factory=ConventionConfig)
    hooks: HooksConfig = field(default_factory=HooksConfig)
    verify: VerifyConfig = field(default_factory=VerifyConfig)
    guards: GuardsConfig = field(default_factory=GuardsConfig)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("path", None)
        return data

    @classmethod
    def from_dict(cls, path: Path, data: dict[str, Any]) -> RepoConfig:
        whitelist_data = data.get("whitelist", {}) if isinstance(data.get("whitelist"), dict) else {}
        timeline_data = data.get("timeline", {}) if isinstance(data.get("timeline"), dict) else {}
        conventions_data = data.get("conventions", {}) if isinstance(data.get("conventions"), dict) else {}
        hooks_data = data.get("hooks", {}) if isinstance(data.get("hooks"), dict) else {}
        verify_data = data.get("verify", {}) if isinstance(data.get("verify"), dict) else {}
        guards_data = data.get("guards", {}) if isinstance(data.get("guards"), dict) else {}

        return cls(
            path=path,
            version=data.get("version", CURRENT_CONFIG_VERSION),
            whitelist=WhitelistConfig(
                enabled=whitelist_data.get("enabled", True),
                allowed_emails=list(whitelist_data.get("allowed_emails", [])),
            ),
            timeline=TimelineConfig(
                enabled=timeline_data.get("enabled", False),
                timezone=timeline_data.get("timezone", DEFAULT_TIMEZONE),
                start=timeline_data.get("start", DEFAULT_START),
                end=timeline_data.get("end", DEFAULT_END),
                min_gap_seconds=timeline_data.get("min_gap_seconds", DEFAULT_MIN_GAP_SECONDS),
            ),
            conventions=ConventionConfig(
                language=conventions_data.get("language", "en"),
                style=conventions_data.get("style", "conventional"),
                template=conventions_data.get(
                    "template",
                    "<type>(<scope>): <subject>\n\n<summary>\n- <bullet point 1>\n- <bullet point 2>",
                ),
                rules=list(conventions_data.get("rules", [])),
            ),
            hooks=HooksConfig(
                policy=hooks_data.get("policy", DEFAULT_HOOKS_POLICY),
            ),
            verify=VerifyConfig(
                enabled=verify_data.get("enabled", True),
                test=verify_data.get("test", ""),
                lint=verify_data.get("lint", ""),
            ),
            guards=GuardsConfig(
                enabled=guards_data.get("enabled", True),
                scan_secrets=guards_data.get("scan_secrets", True),
                protected_branches=list(guards_data.get("protected_branches", [])),
                deny_paths=list(guards_data.get("deny_paths", [])),
                allow_paths=list(guards_data.get("allow_paths", [])),
            ),
        )


def needs_migration(config: RepoConfig) -> bool:
    return config.version < CURRENT_CONFIG_VERSION


def migrate_config(config: RepoConfig) -> RepoConfig:
    config.version = CURRENT_CONFIG_VERSION
    return config


def git_dir(cwd: Path | None = None) -> Path:
    """This checkout's git dir — `.git/worktrees/<name>` inside a worktree."""
    return _resolve_git_dir("--git-dir", cwd=cwd)


def common_git_dir(cwd: Path | None = None) -> Path:
    """The git dir shared by every worktree — the main `.git`, from anywhere.

    Configuration belongs here, not in `git_dir()`. Keyed by the per-worktree
    dir, a second checkout of the same repository found no config, fell through
    to the global one, and quietly committed under different rules than the
    repository had set — a divergence with nothing to notice it by.
    """
    return _resolve_git_dir("--git-common-dir", cwd=cwd)


def _resolve_git_dir(flag: str, *, cwd: Path | None) -> Path:
    raw = gitutil.run(["rev-parse", flag], cwd=cwd).strip()
    path = Path(raw)
    if not path.is_absolute():
        root = gitutil.repo_root(cwd=cwd)
        path = (root / path).resolve()
    return path


def repo_config_path(cwd: Path | None = None) -> Path:
    return common_git_dir(cwd=cwd) / "agentkit-commit.json"


def load_repo_config(cwd: Path | None = None, *, auto_migrate: bool = False) -> RepoConfig | None:
    try:
        path = repo_config_path(cwd=cwd)
    except Exception:
        return None

    if not path.is_file():
        # A worktree onboarded before configuration moved to the common dir
        # keeps its own file. Reading it is what stops the upgrade from
        # silently dropping that worktree back to the global config; the next
        # save writes to the shared path and the stale copy stops mattering.
        legacy = git_dir(cwd=cwd) / "agentkit-commit.json"
        if not legacy.is_file():
            return None
        path = legacy

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
            fix="agentkit commit onboard --force",
            what_to_report="Repository commit configuration file is corrupted.",
            details=["Fix the JSON syntax or re-run onboarding: `agentkit commit onboard --force`."],
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
            "language": "en",
            "style": "conventional",
            "sample_subjects": [],
            "suggested_template": "<type>(<scope>): <short subject line>\n\n[Optional] Overview of intent or motivation\n\n- <Key change 1>\n- <Key change 2>",
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
