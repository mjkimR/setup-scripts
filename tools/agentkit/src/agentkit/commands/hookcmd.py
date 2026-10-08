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
from ..commitsafe.message import strip_co_authored_by as clean_co_authors
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


def _resolve_verbosity(
    cwd: Path | None = None,
    is_verbose: bool | None = None,
    is_quiet: bool | None = None,
) -> str:
    """Determine the hook verbosity level (quiet, compact, verbose).

    Precedence:
    1. CLI flags (--verbose / --quiet)
    2. Environment variables: AGENTKIT_HOOK_VERBOSITY, AGENTKIT_VERBOSE, AGENTKIT_QUIET
    3. Git config: agentkit.hooks.verbosity, agentkit.hooks.quiet
    4. Repository config: cfg.hooks.verbosity
    5. Default: "quiet"
    """
    if is_verbose:
        return "verbose"
    if is_quiet:
        return "quiet"

    env_verb = os.environ.get("AGENTKIT_HOOK_VERBOSITY")
    if env_verb in ("quiet", "compact", "verbose"):
        return env_verb
    if os.environ.get("AGENTKIT_VERBOSE") == "1":
        return "verbose"
    if os.environ.get("AGENTKIT_QUIET") == "1":
        return "quiet"

    try:
        root = gitutil.repo_root(cwd=cwd)
    except Exception:
        root = cwd or Path.cwd()

    git_verb = gitutil.config_value("agentkit.hooks.verbosity", cwd=root)
    if git_verb in ("quiet", "compact", "verbose"):
        return git_verb

    git_quiet = gitutil.config_bool("agentkit.hooks.quiet", cwd=root)
    if git_quiet is False:
        return "verbose"
    elif git_quiet is True:
        return "quiet"

    cfg = load_repo_config(cwd=root)
    if cfg is not None and getattr(cfg.hooks, "verbosity", None) in ("quiet", "compact", "verbose"):
        return cfg.hooks.verbosity

    return "quiet"


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
@click.option("--verbose", "-v", "is_verbose", is_flag=True, default=False, help="Force verbose hook output.")
@click.option("--quiet", "-q", "is_quiet", is_flag=True, default=False, help="Force quiet hook output.")
def run_pre_commit(is_verbose: bool, is_quiet: bool) -> None:
    """Run pre-commit checks: whitelist, guardrails (branch, secrets, denied paths), and repo verify."""
    root = gitutil.repo_root()
    verbosity = _resolve_verbosity(cwd=root, is_verbose=is_verbose, is_quiet=is_quiet)

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
        if verbosity in ("compact", "verbose"):
            click.echo("[hook:pre-commit] [SKIP] Verification bypassed via git config (agentkit.verify=false)")
            click.echo("[hook:pre-commit] [OK] All checks passed.")
        return

    cfg = load_repo_config(cwd=root)
    should_verify = (verify_override is True) or (cfg is not None and cfg.verify.enabled)
    if should_verify and cfg is not None:
        commands = cfg.verify.configured()
        if commands:
            # Check if this is an intermediate commit with bypass-intermediate policy
            if cfg.hooks.policy == "bypass-intermediate":
                pending_changes = gitutil.pending(cwd=root)
                # If there are still unstaged or untracked changes, skip verification
                has_unstaged = any(line[1:2] in ("M", "D", "?") or line.startswith("??") for line in pending_changes)
                if has_unstaged:
                    if verbosity in ("compact", "verbose"):
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
                    if verbosity == "verbose":
                        click.echo(f"[hook:pre-commit] $ {cmd}")
                        result = subprocess.run(cmd, shell=True, cwd=root, env=verify_env)
                    else:
                        result = subprocess.run(
                            cmd, shell=True, cwd=root, env=verify_env, capture_output=True, text=True
                        )

                    if result.returncode != 0:
                        click.echo(
                            f"[hook:pre-commit] [FAIL] '{name}' check failed (exit {result.returncode}).",
                            err=True,
                        )
                        click.echo(f"$ {cmd}", err=True)
                        output_parts = []
                        if hasattr(result, "stdout") and result.stdout:
                            output_parts.append(result.stdout.strip())
                        if hasattr(result, "stderr") and result.stderr:
                            output_parts.append(result.stderr.strip())
                        output = "\n".join(p for p in output_parts if p).strip()
                        if output:
                            lines = output.splitlines()
                            if len(lines) > 25:
                                click.echo(f"--- Output (last 25 lines of {len(lines)}) ---", err=True)
                                click.echo("\n".join(lines[-25:]), err=True)
                            else:
                                click.echo(output, err=True)
                        click.echo(f"\n[hint] To re-run this check directly: {cmd}", err=True)
                        click.echo(
                            "[hint] To bypass verify for intermediate commit: git -c agentkit.verify=false commit -m '...'",
                            err=True,
                        )
                        sys.exit(result.returncode)

                    if verbosity == "compact":
                        click.echo(f"[hook:pre-commit] ✓ {name} passed")

    if verbosity in ("compact", "verbose"):
        click.echo("[hook:pre-commit] [OK] All checks passed.")


@hook_group.command("run-commit-msg")
@click.argument("msg_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--strip-co-authored-by/--no-strip-co-authored-by",
    "strip_co_authored_by",
    default=None,
    help="Strip Co-Authored-By lines from commit message.",
)
@click.option("--verbose", "-v", "is_verbose", is_flag=True, default=False, help="Force verbose hook output.")
@click.option("--quiet", "-q", "is_quiet", is_flag=True, default=False, help="Force quiet hook output.")
def run_commit_msg(
    msg_file: Path,
    strip_co_authored_by: bool | None,
    is_verbose: bool,
    is_quiet: bool,
) -> None:
    """Validate commit message format and conventions, stripping co-authors if configured."""
    root = gitutil.repo_root()
    verbosity = _resolve_verbosity(cwd=root, is_verbose=is_verbose, is_quiet=is_quiet)

    cfg = load_repo_config(cwd=root)
    if strip_co_authored_by is not None:
        should_strip = strip_co_authored_by
    else:
        strip_override = gitutil.config_bool("agentkit.strip-co-authored-by", cwd=root)
        if strip_override is None:
            strip_override = gitutil.config_bool("agentkit.strip_co_authored_by", cwd=root)
        if strip_override is not None:
            should_strip = strip_override
        elif cfg is not None:
            should_strip = cfg.conventions.strip_co_authored_by
        else:
            should_strip = True

    raw_text = msg_file.read_text(encoding="utf-8")
    if should_strip:
        cleaned = clean_co_authors(raw_text)
        if cleaned != raw_text:
            new_content = f"{cleaned}\n" if cleaned else ""
            msg_file.write_text(new_content, encoding="utf-8")
            raw_text = new_content
            if verbosity in ("compact", "verbose"):
                click.echo("[hook:commit-msg] Stripped Co-Authored-By trailer(s).")

    lines = [line.strip() for line in raw_text.splitlines() if not line.strip().startswith("#")]
    non_empty = [line for line in lines if line]

    if not non_empty:
        click.echo("[hook:commit-msg] [FAIL] Commit message cannot be empty.", err=True)
        sys.exit(1)

    header = non_empty[0]
    if cfg is not None and cfg.conventions.style.lower() == "conventional" and not CONVENTIONAL_PATTERN.match(header):
        click.echo(
            f"[hook:commit-msg] [WARN] Commit header '{header}' does not follow conventional commit pattern "
            "(e.g., 'feat: description' or 'fix(scope): description').",
            err=True,
        )
        # We warn rather than hard-block to avoid blocking manual amends or merge commits,
        # but it clearly informs the developer/agent.

    if verbosity in ("compact", "verbose"):
        click.echo("[hook:commit-msg] [OK] Commit message verified.")


def _handle_auto_push(repo_cfg, root: Path, verbosity: str) -> None:
    if not repo_cfg.push.enabled:
        return

    # Avoid duplicate push when agentkit commitsafe is explicitly handling it
    if os.environ.get("AGENTKIT_COMMITSAFE_PUSH") == "1":
        return

    # Skip push during intermediate commit with bypass-intermediate policy
    if repo_cfg.hooks.policy == "bypass-intermediate":
        pending_changes = gitutil.pending(cwd=root)
        has_unstaged = any(line[1:2] in ("M", "D", "?") or line.startswith("??") for line in pending_changes)
        if has_unstaged:
            if verbosity in ("compact", "verbose"):
                click.echo("[hook:post-commit] [SKIP] Auto-push skipped for intermediate commit")
            return

    # Check git config override to bypass auto-push (e.g. git -c agentkit.push=false commit ...)
    push_override = gitutil.config_bool("agentkit.push", cwd=root)
    if push_override is False:
        if verbosity in ("compact", "verbose"):
            click.echo("[hook:post-commit] [SKIP] Auto-push bypassed via git config (agentkit.push=false)")
        return

    # When no explicit target branch is configured, git pushes the current branch.
    # Skip auto-push if current branch has no upstream tracking branch
    # unless push.autoSetupRemote is enabled.
    if not repo_cfg.push.branch:
        auto_setup = gitutil.config_bool("push.autoSetupRemote", cwd=root)
        if not auto_setup and not gitutil.has_upstream(cwd=root):
            if verbosity in ("compact", "verbose"):
                click.echo("[hook:post-commit] [SKIP] Auto-push skipped: no upstream branch configured")
            return

    push_argv = ["git", "push"]
    if repo_cfg.push.remote:
        push_argv.append(repo_cfg.push.remote)
        if repo_cfg.push.branch:
            push_argv.append(repo_cfg.push.branch)

    push_env = os.environ.copy()
    for git_var in (
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_PREFIX",
        "GIT_COMMON_DIR",
    ):
        push_env.pop(git_var, None)

    target_desc = (
        f"{repo_cfg.push.remote or 'default remote'}{(' ' + repo_cfg.push.branch) if repo_cfg.push.branch else ''}"
    )
    push_res = subprocess.run(
        push_argv,
        cwd=str(root),
        env=push_env,
        capture_output=True,
        text=True,
    )
    if push_res.returncode == 0:
        click.echo(f"[hook:post-commit] [PUSH] Auto-pushed to {target_desc}.")
    else:
        err_msg = push_res.stderr.strip()
        if "no upstream branch" in err_msg.lower():
            if verbosity in ("compact", "verbose"):
                click.echo("[hook:post-commit] [SKIP] Auto-push skipped: no upstream branch configured")
        else:
            click.echo(f"[hook:post-commit] [ERROR] Auto-push failed: {err_msg}", err=True)
            click.echo(f"[hint] To push manually: {' '.join(push_argv)}", err=True)


@hook_group.command("run-post-commit")
@click.option("--verbose", "-v", "is_verbose", is_flag=True, default=False, help="Force verbose hook output.")
@click.option("--quiet", "-q", "is_quiet", is_flag=True, default=False, help="Force quiet hook output.")
def run_post_commit(is_verbose: bool, is_quiet: bool) -> None:
    """Run post-commit actions: apply virtual timeline timestamp and auto-push if enabled."""
    # Avoid infinite recursion during git commit --amend
    if os.environ.get("AGENTKIT_POST_COMMIT_AMENDING") == "1":
        return

    root = gitutil.repo_root()
    verbosity = _resolve_verbosity(cwd=root, is_verbose=is_verbose, is_quiet=is_quiet)

    repo_cfg = load_repo_config(cwd=root)
    if repo_cfg is None:
        return

    # 1. Timeline timestamp
    if repo_cfg.timeline.enabled:
        timeline_override = gitutil.config_bool("agentkit.timeline", cwd=root)
        if timeline_override is not False:
            try:
                config, _ = checked_identity(cwd=root)
                stamp = resolve(config)
                if stamp.enabled:
                    stamp_str = stamp.format()
                    if verbosity in ("compact", "verbose"):
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
                        click.echo(
                            f"[hook:post-commit] [WARN] Failed to apply timeline: {result.stderr.strip()}", err=True
                        )
            except Exception as error:
                click.echo(f"[hook:post-commit] [WARN] Timeline post-commit failed: {error}", err=True)

    # 2. Auto-push
    _handle_auto_push(repo_cfg, root, verbosity)
