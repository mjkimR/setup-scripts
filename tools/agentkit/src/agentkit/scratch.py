"""Per-repository scratch space for agent working files.

Skills that need somewhere to put working files (handoff documents, generated
reports, intermediate state) resolve one root through here instead of inventing
their own locations. The root lives in the working tree — visible in an IDE's
project tree, unlike anything under `.git/` — and is kept out of `git status`
via `<common-git-dir>/info/exclude`, so adopting it never dirties the tree.

Configuration is stored per-repository at `<git-dir>/agentkit-scratch.json`.
First use falls back to `.agents/tmp` and records that choice, so `path` works
without onboarding; `onboard` exists to override it.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from . import gitutil
from .errors import ConfigError, GitCommandError, NotAGitRepoError
from .repoconfig import git_dir

DEFAULT_ROOT = ".agents/tmp"
DEFAULT_CLEAN_OLDER_THAN = "30d"
CURRENT_CONFIG_VERSION = 1

# How the root is kept out of `git status`.
MECHANISM_EXISTING = "existing"  # already ignored before we arrived
MECHANISM_INFO_EXCLUDE = "info-exclude"  # repo-local, never touches the tree
MECHANISM_GITIGNORE = "gitignore"  # committed, shared with the team

_DURATION = re.compile(r"^(\d+)([smhd]?)$")
_UNIT_SECONDS = {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_duration(value: str) -> int:
    """Parse a duration string (e.g. '30d', '12h', '30m', '60s') into seconds."""
    match = _DURATION.match(value.strip())
    if not match:
        raise ConfigError(
            f"invalid duration {value!r} (expected e.g. 30d, 24h, 60m, 300s).",
            fix="Pass a valid duration to --older-than, e.g. --older-than 30d",
        )
    return int(match.group(1)) * _UNIT_SECONDS[match.group(2)]


@dataclass
class ScratchConfig:
    version: int = CURRENT_CONFIG_VERSION
    root: str = DEFAULT_ROOT
    mechanism: str = MECHANISM_INFO_EXCLUDE

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScratchConfig:
        return cls(
            version=data.get("version", CURRENT_CONFIG_VERSION),
            root=data.get("root", DEFAULT_ROOT),
            mechanism=data.get("mechanism", MECHANISM_INFO_EXCLUDE),
        )


@dataclass
class ScratchResolution:
    path: Path  # the requested directory (root, or root/subdir), created
    root: Path  # the scratch root
    in_repo: bool
    onboarded: bool = False  # True when this call created the configuration
    mechanism: str | None = None


def scratch_config_path(cwd: Path | None = None) -> Path:
    return git_dir(cwd=cwd) / "agentkit-scratch.json"


def load_scratch_config(cwd: Path | None = None) -> ScratchConfig | None:
    path = scratch_config_path(cwd=cwd)
    if not path.is_file():
        return None
    try:
        return ScratchConfig.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError) as error:
        raise ConfigError(
            f"failed to read scratch config at {path}: {error}",
            fix="agentkit scratch onboard --force",
            what_to_report="Repository scratch configuration file is corrupted.",
            details=["Fix the JSON syntax or re-run onboarding: `agentkit scratch onboard --force`."],
        ) from error


def save_scratch_config(config: ScratchConfig, cwd: Path | None = None) -> Path:
    path = scratch_config_path(cwd=cwd)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path


def validate_relative_dir(value: str, *, what: str) -> str:
    """A repo-relative POSIX path that cannot escape the repository."""
    candidate = value.strip().strip("/")
    parts = PurePosixPath(candidate).parts
    if not candidate or Path(value).is_absolute() or "\\" in value:
        raise ConfigError(
            f"{what} must be a relative POSIX path inside the repository, got {value!r}.",
            fix="agentkit scratch onboard --root <relative-dir> --force",
        )
    if ".." in parts or parts[0] == ".git":
        raise ConfigError(
            f"{what} may not escape the repository or live under .git/, got {value!r}.",
            fix="agentkit scratch onboard --root <relative-dir> --force",
        )
    return str(PurePosixPath(candidate))


def is_ignored(rel_path: str, repo_root: Path) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "-q", "--", rel_path],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    if result.returncode in (0, 1):
        return result.returncode == 0
    detail = result.stderr.strip() or str(result.returncode)
    raise GitCommandError(
        f"git check-ignore -q -- {rel_path} failed: {detail}",
        what_to_report=f"A git command failed unexpectedly: git check-ignore {rel_path}.",
        details=[detail],
    )


def common_git_dir(cwd: Path | None = None) -> Path:
    """The shared git dir — where info/exclude lives, even from a worktree."""
    raw = gitutil.run(["rev-parse", "--git-common-dir"], cwd=cwd).strip()
    path = Path(raw)
    if not path.is_absolute():
        path = (gitutil.repo_root(cwd=cwd) / path).resolve()
    return path


def _append_ignore_line(file: Path, pattern: str, header: str | None) -> None:
    existing = file.read_text(encoding="utf-8") if file.is_file() else ""
    if pattern in {line.strip() for line in existing.splitlines()}:
        return
    file.parent.mkdir(parents=True, exist_ok=True)
    prefix = existing if existing.endswith("\n") or not existing else existing + "\n"
    block = f"{header}\n{pattern}\n" if header and not existing else f"{pattern}\n"
    file.write_text(prefix + block, encoding="utf-8")


def ensure_ignored(root_rel: str, repo_root: Path, *, shared: bool = False) -> str:
    """Make sure the scratch root never shows up in `git status`.

    Returns the mechanism used. `info/exclude` is the default because writing
    `.gitignore` is itself a tree change that would need a commit.
    """
    if is_ignored(root_rel, repo_root):
        return MECHANISM_EXISTING
    pattern = f"/{root_rel}/"
    if shared:
        _append_ignore_line(repo_root / ".gitignore", pattern, header=None)
        return MECHANISM_GITIGNORE
    exclude = common_git_dir(cwd=repo_root) / "info" / "exclude"
    _append_ignore_line(exclude, pattern, header="# agentkit scratch space")
    return MECHANISM_INFO_EXCLUDE


def _fallback_base(cwd: Path) -> Path:
    slug = str(cwd.resolve()).replace(os.sep, "-").lstrip("-")
    return Path.home() / ".agents" / "tmp" / slug


def resolve_scratch(cwd: Path | None = None, subdir: str | None = None) -> ScratchResolution:
    """Resolve (and create) the scratch directory for the current repository.

    Unconfigured repositories are onboarded on the spot with the default root,
    so callers never fail for lack of setup. Outside a git repository the root
    falls back under `~/.agents/tmp/`, keyed by directory.
    """
    where = (cwd or Path.cwd()).resolve()
    try:
        repo_root = gitutil.repo_root(cwd=where)
    except NotAGitRepoError:
        resolution = ScratchResolution(path=_fallback_base(where), root=_fallback_base(where), in_repo=False)
    else:
        config = load_scratch_config(cwd=repo_root)
        onboarded = config is None
        if config is None:
            config = ScratchConfig()
        root_rel = validate_relative_dir(config.root, what="scratch root")
        # Re-ensure on every resolve: cheap, idempotent, and it heals a
        # hand-edited exclude file before the tree gets dirtied.
        mechanism = ensure_ignored(root_rel, repo_root)
        if onboarded:
            config.mechanism = mechanism
            save_scratch_config(config, cwd=repo_root)
        root = repo_root / root_rel
        resolution = ScratchResolution(path=root, root=root, in_repo=True, onboarded=onboarded, mechanism=mechanism)

    if subdir:
        resolution.path = resolution.root / validate_relative_dir(subdir, what="subdir")
    resolution.path.mkdir(parents=True, exist_ok=True)
    return resolution


def clean_scratch(
    max_age_seconds: int,
    *,
    delete: bool = False,
    cwd: Path | None = None,
) -> list[Path]:
    """Find and optionally delete files under the scratch root older than max_age_seconds.

    When delete=True, deletes matching files and prunes empty directories under the root.
    Never follows symlinks and never modifies anything outside the scratch root.
    Returns the list of affected file paths.
    """
    resolution = resolve_scratch(cwd=cwd)
    root = resolution.root
    if not root.is_dir():
        return []

    cutoff = time.time() - max_age_seconds
    affected: list[Path] = []

    for dirpath_str, _dirnames, filenames in os.walk(root, topdown=False, followlinks=False):
        dirpath = Path(dirpath_str)
        for name in filenames:
            file_path = dirpath / name
            try:
                stat = file_path.lstat()
            except OSError:
                continue

            if stat.st_mtime <= cutoff:
                affected.append(file_path)
                if delete:
                    with contextlib.suppress(OSError):
                        file_path.unlink()

        if delete and dirpath.resolve() != root.resolve():
            with contextlib.suppress(OSError):
                dirpath.rmdir()

    affected.sort()
    return affected
