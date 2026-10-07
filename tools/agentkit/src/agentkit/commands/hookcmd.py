"""Git hooks management and execution commands for agentkit."""

from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import click

from .. import gitutil
from ..commitsafe import checked_identity, resolve
from ..commitsafe import guards as guards_module
from ..errors import AgentkitError
from ..repoconfig import common_git_dir, load_repo_config, save_repo_config

HOOK_MARKER = "# Managed by agentkit"

PRE_COMMIT_SCRIPT = f"""#!/usr/bin/env bash
{HOOK_MARKER}
exec agentkit hook run-pre-commit "$@"
"""

COMMIT_MSG_SCRIPT = f"""#!/usr/bin/env bash
{HOOK_MARKER}
exec agentkit hook run-commit-msg "$@"
"""

POST_COMMIT_SCRIPT = f"""#!/usr/bin/env bash
{HOOK_MARKER}
exec agentkit hook run-post-commit "$@"
"""

CONVENTIONAL_PATTERN = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([a-zA-Z0-9_\-\.\/]+\))?!?: .+"
)


def _get_hooks_dir(cwd: Path | None = None) -> Path:
    hooks_dir = common_git_dir(cwd=cwd) / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    return hooks_dir


@click.group("hook")
def hook_group() -> None:
    """Manage and execute git repository hooks."""


@hook_group.command("install")
@click.option("--force", is_flag=True, help="Overwrite non-agentkit hooks after backing them up.")
def install(force: bool) -> None:
    """Install git hooks (pre-commit, commit-msg, post-commit) in the repository."""
    hooks_dir = _get_hooks_dir()
    targets = [
        ("pre-commit", PRE_COMMIT_SCRIPT),
        ("commit-msg", COMMIT_MSG_SCRIPT),
        ("post-commit", POST_COMMIT_SCRIPT),
    ]

    installed_hooks = []
    for hook_name, content in targets:
        hook_path = hooks_dir / hook_name
        if hook_path.exists():
            current_content = hook_path.read_text(encoding="utf-8")
            if HOOK_MARKER not in current_content:
                backup_path = hooks_dir / f"{hook_name}.bak"
                hook_path.rename(backup_path)
                click.echo(f"[hook:install] [BACKUP] Existing {hook_name} moved to {backup_path.name}")
        hook_path.write_text(content, encoding="utf-8")
        # Ensure executable
        hook_path.chmod(hook_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        installed_hooks.append(hook_name)

    cfg = load_repo_config()
    if cfg is not None:
        cfg.hooks.installed = True
        save_repo_config(cfg)

    click.echo(f"[hook:install] [SUCCESS] Installed git hooks ({', '.join(installed_hooks)}) in {hooks_dir}")


@hook_group.command("uninstall")
def uninstall() -> None:
    """Remove agentkit git hooks and restore any backups."""
    hooks_dir = _get_hooks_dir()
    targets = ["pre-commit", "commit-msg", "post-commit"]
    uninstalled = []

    for hook_name in targets:
        hook_path = hooks_dir / hook_name
        if hook_path.exists():
            content = hook_path.read_text(encoding="utf-8")
            if HOOK_MARKER in content:
                hook_path.unlink()
                uninstalled.append(hook_name)
                backup_path = hooks_dir / f"{hook_name}.bak"
                if backup_path.exists():
                    backup_path.rename(hook_path)
                    click.echo(f"[hook:uninstall] Restored original {hook_name} from backup")

    cfg = load_repo_config()
    if cfg is not None:
        cfg.hooks.installed = False
        save_repo_config(cfg)

    click.echo(
        f"[hook:uninstall] [SUCCESS] Uninstalled git hooks ({', '.join(uninstalled) if uninstalled else 'none'})"
    )


@hook_group.command("status")
def status() -> None:
    """Display the installation status of git hooks."""
    hooks_dir = _get_hooks_dir()
    targets = ["pre-commit", "commit-msg", "post-commit"]
    cfg = load_repo_config()
    cfg_installed = cfg.hooks.installed if cfg else False

    click.echo(f"Git hooks directory: {hooks_dir}")
    click.echo(f"Repository config hooks.installed: {'[ON]' if cfg_installed else '[OFF]'}")
    for hook_name in targets:
        hook_path = hooks_dir / hook_name
        if not hook_path.exists():
            click.echo(f"  • {hook_name}: [NOT INSTALLED]")
        else:
            content = hook_path.read_text(encoding="utf-8")
            managed = HOOK_MARKER in content
            status_text = "[INSTALLED: managed by agentkit]" if managed else "[INSTALLED: custom hook]"
            click.echo(f"  • {hook_name}: {status_text}")


@hook_group.command("run-pre-commit")
def run_pre_commit() -> None:
    """Run pre-commit checks: whitelist, guardrails (branch, secrets, denied paths), and repo verify."""
    root = gitutil.repo_root()

    # 0. Whitelist / Identity check
    try:
        checked_identity(cwd=root)
    except AgentkitError as error:
        click.echo(f"[hook:pre-commit] [BLOCKED] {error}", err=True)
        if error.advisory.details:
            for d in error.advisory.details:
                click.echo(f"  {d}", err=True)
        sys.exit(1)
    except Exception as error:
        click.echo(f"[hook:pre-commit] [ERROR] Identity check failed: {error}", err=True)
        sys.exit(1)

    # 1. Guards check
    guards = guards_module.load_guards()
    exempt_env = os.environ.get("AGENTKIT_ALLOW_SECRET", "")
    allow_secret = tuple(p.strip() for p in exempt_env.split(",") if p.strip())
    try:
        guards_module.check(guards, cwd=Path.cwd(), allow_secret=allow_secret)
    except AgentkitError as error:
        click.echo(f"[hook:pre-commit] [BLOCKED] {error}", err=True)
        if error.advisory.details:
            for d in error.advisory.details:
                click.echo(f"  {d}", err=True)
        sys.exit(1)
    except Exception as error:
        click.echo(f"[hook:pre-commit] [ERROR] Guard check failed: {error}", err=True)
        sys.exit(1)

    # 2. Repo verify checks
    root = gitutil.repo_root()
    verify_override = gitutil.config_bool("agentkit.verify", cwd=root)
    if verify_override is False:
        click.echo("[hook:pre-commit] [SKIP] Verification bypassed via git config (agentkit.verify=false)")
        click.echo("[hook:pre-commit] [OK] All checks passed.")
        return

    cfg = load_repo_config()
    should_verify = (verify_override is True) or (cfg is not None and cfg.verify.enabled)
    if should_verify and cfg is not None:
        commands = cfg.verify.configured()
        if commands:
            # Check if this is an intermediate commit with bypass-intermediate policy
            if cfg.hooks.policy == "bypass-intermediate":
                pending_changes = gitutil.pending()
                # If there are still unstaged or untracked changes, skip verification
                has_unstaged = any(line[1:2] in ("M", "D", "?") or line.startswith("??") for line in pending_changes)
                if has_unstaged:
                    click.echo("[hook:pre-commit] [SKIP] Intermediate commit with policy=bypass-intermediate")
                    click.echo("[hook:pre-commit] [OK] All checks passed.")
                    return

            # Clean git hook repository & transaction variables so test suites run in pristine isolation
            verify_env = os.environ.copy()
            for git_var in (
                "GIT_DIR",
                "GIT_WORK_TREE",
                "GIT_INDEX_FILE",
                "GIT_PREFIX",
                "GIT_COMMON_DIR",
                "GIT_GRAFT_FILE",
                "GIT_AUTHOR_DATE",
                "GIT_COMMITTER_DATE",
                "GIT_AUTHOR_NAME",
                "GIT_AUTHOR_EMAIL",
                "GIT_COMMITTER_NAME",
                "GIT_COMMITTER_EMAIL",
                "GIT_COMMIT_SAFE_EMAIL",
            ):
                verify_env.pop(git_var, None)

            with gitutil.staged_snapshot(cwd=root):
                for name, cmd in commands:
                    click.echo(f"[hook:pre-commit] $ {cmd}")
                    result = subprocess.run(cmd, shell=True, cwd=root, env=verify_env)
                    if result.returncode != 0:
                        click.echo(f"[hook:pre-commit] [FAIL] {name} failed (exit {result.returncode}).", err=True)
                        sys.exit(result.returncode)

    click.echo("[hook:pre-commit] [OK] All checks passed.")


@hook_group.command("run-commit-msg")
@click.argument("msg_file", type=click.Path(exists=True, path_type=Path))
def run_commit_msg(msg_file: Path) -> None:
    """Validate commit message format and conventions."""
    raw_text = msg_file.read_text(encoding="utf-8")
    lines = [line.strip() for line in raw_text.splitlines() if not line.strip().startswith("#")]
    non_empty = [line for line in lines if line]

    if not non_empty:
        click.echo("[hook:commit-msg] [FAIL] Commit message cannot be empty.", err=True)
        sys.exit(1)

    header = non_empty[0]
    cfg = load_repo_config()
    if cfg is not None and cfg.conventions.style.lower() == "conventional" and not CONVENTIONAL_PATTERN.match(header):
        click.echo(
            f"[hook:commit-msg] [WARN] Commit header '{header}' does not follow conventional commit pattern "
            "(e.g., 'feat: description' or 'fix(scope): description').",
            err=True,
        )
        # We warn rather than hard-block to avoid blocking manual amends or merge commits,
        # but it clearly informs the developer/agent.

    click.echo("[hook:commit-msg] [OK] Commit message verified.")


@hook_group.command("run-post-commit")
def run_post_commit() -> None:
    """Run post-commit actions: apply virtual timeline timestamp if enabled."""
    # Avoid infinite recursion during git commit --amend
    if os.environ.get("AGENTKIT_POST_COMMIT_AMENDING") == "1":
        return

    root = gitutil.repo_root()
    repo_cfg = load_repo_config(cwd=root)
    if repo_cfg is None or not repo_cfg.timeline.enabled:
        return

    # Check git config override to bypass timeline (e.g. git -c agentkit.timeline=false commit ...)
    timeline_override = gitutil.config_bool("agentkit.timeline", cwd=root)
    if timeline_override is False:
        return

    try:
        config, _ = checked_identity(cwd=root)
        stamp = resolve(config)
        if not stamp.enabled:
            return

        stamp_str = stamp.format()
        click.echo(f"[hook:post-commit] Applying virtual timeline: {stamp_str}")

        amend_env = {
            **os.environ,
            "AGENTKIT_POST_COMMIT_AMENDING": "1",
            "GIT_AUTHOR_DATE": stamp_str,
            "GIT_COMMITTER_DATE": stamp_str,
        }
        for git_var in ("GIT_INDEX_FILE", "GIT_DIR", "GIT_WORK_TREE", "GIT_PREFIX"):
            amend_env.pop(git_var, None)

        result = subprocess.run(
            ["git", "commit", "--amend", "--no-edit", "--no-verify", f"--date={stamp_str}"],
            cwd=str(root),
            env=amend_env,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            click.echo(f"[hook:post-commit] [WARN] Failed to apply timeline: {result.stderr.strip()}", err=True)
    except Exception as error:
        click.echo(f"[hook:post-commit] [WARN] Timeline post-commit failed: {error}", err=True)
