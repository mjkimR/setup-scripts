"""`agentkit commit` — per-repository configuration, onboarding, and history analysis."""

from __future__ import annotations

import json
import subprocess
from typing import Any

import click

from .. import gitutil
from ..repoconfig import (
    DEFAULT_HOOKS_POLICY,
    HOOKS_POLICIES,
    ConventionConfig,
    HooksConfig,
    RepoConfig,
    TimelineConfig,
    VerifyConfig,
    WhitelistConfig,
    analyze_repo_history,
    ensure_supported_hooks_policy,
    load_repo_config,
    repo_config_path,
    save_repo_config,
)


@click.group("commit")
def commit_group() -> None:
    """Manage per-repository commit configurations and onboarding."""


@commit_group.command("analyze")
@click.option("--count", default=25, show_default=True, help="Number of commits to analyze.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def analyze(count: int, as_json: bool) -> None:
    """Analyze recent git history to infer commit conventions, language, and author identity."""
    data = analyze_repo_history(count=count)

    if as_json:
        click.echo(json.dumps(data, indent=2, ensure_ascii=False))
        return

    click.echo("=== Repository Commit History Analysis ===")
    click.echo(f"  Total analyzed:     {data['total_commits']} commits")
    click.echo(f"  Primary email:      {data['primary_email']}")
    click.echo(f"  Detected language:  {data['language']} ({'Korean' if data['language'] == 'ko' else 'English'})")
    click.echo(f"  Detected style:     {data['style']}")
    if data["emails"]:
        click.echo(f"  Observed emails:    {', '.join(data['emails'][:5])}")
    click.echo("\n--- Suggested Template ---")
    click.echo(data["suggested_template"])
    if data["sample_subjects"]:
        click.echo("\n--- Recent Sample Subjects ---")
        for s in data["sample_subjects"]:
            click.echo(f"  • {s}")


@commit_group.command("config")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@click.option(
    "--set",
    "set_pair",
    metavar="KEY=VALUE",
    help="Update a config key (e.g. whitelist.enabled=false, conventions.language=en).",
)
def show_config(as_json: bool, set_pair: str | None) -> None:
    """Show or update the current repository's commit configuration."""
    cfg = load_repo_config()

    if set_pair:
        if cfg is None:
            raise click.ClickException("Repository is not onboarded yet. Run `agentkit commit onboard` first.")
        if "=" not in set_pair:
            raise click.ClickException("Invalid format for --set. Use KEY=VALUE (e.g. whitelist.enabled=false).")

        key, value = set_pair.split("=", 1)
        key = key.strip()
        value = value.strip()

        _set_nested(cfg, key, value)
        # Refuse before saving, so the config file never holds a policy the
        # runner would refuse at handoff time anyway.
        if key == "hooks.policy":
            ensure_supported_hooks_policy(value)
        save_repo_config(cfg)
        click.echo(f"[SUCCESS] Updated {key} = {value}")

    if cfg is None:
        path = repo_config_path()
        click.echo(f"[INFO] No repository commit config found at: {path}")
        click.echo("[INFO] Run `agentkit commit onboard` to initialize per-repository configuration.")
        return

    if as_json:
        click.echo(json.dumps(cfg.to_dict(), indent=2, ensure_ascii=False))
        return

    click.echo(f"=== Repository Commit Config: {cfg.path} ===")
    click.echo(
        f"  Whitelist:   {'[ON]' if cfg.whitelist.enabled else '[OFF]'} (allowed: {', '.join(cfg.whitelist.allowed_emails) or 'none'})"
    )
    click.echo(
        f"  Timeline:    {'[ON]' if cfg.timeline.enabled else '[OFF]'} "
        f"({cfg.timeline.start}~{cfg.timeline.end} {cfg.timeline.timezone}, min_gap={cfg.timeline.min_gap_seconds}s)"
    )
    click.echo(f"  Language:    {cfg.conventions.language}")
    click.echo(f"  Style:       {cfg.conventions.style}")
    click.echo(f"  Hooks:       {cfg.hooks.policy}")
    click.echo(
        f"  Verify:      {'[ON]' if cfg.verify.enabled else '[OFF]'} "
        f"test: {cfg.verify.test or '(none)'} | lint: {cfg.verify.lint or '(none)'}"
    )
    click.echo("\n--- Template ---")
    click.echo(cfg.conventions.template)


@commit_group.command("verify")
@click.option(
    "--only",
    type=click.Choice(["test", "lint"]),
    default=None,
    help="Run just one of the configured commands.",
)
@click.pass_context
def verify(ctx: click.Context, only: str | None) -> None:
    """Run the repo's configured verify commands, echoing each one first.

    Transparency is the contract: every command is printed verbatim before it
    runs, so what executed is never hidden behind this wrapper. Exit codes:
    0 everything passed (or verification is off / unconfigured — both printed,
    never silent), otherwise the exit code of the first failing command.
    """
    cfg = load_repo_config()
    if cfg is None:
        click.echo("[verify] [INFO] Repository is not onboarded; nothing to verify.")
        return
    if not cfg.verify.enabled:
        click.echo("[verify] [SKIP] Disabled by verify.enabled=false — commits proceed unverified by design.")
        return

    commands = cfg.verify.configured()
    if only:
        commands = [(name, cmd) for name, cmd in commands if name == only]
    if not commands:
        which = f"{only} command" if only else "verify commands"
        click.echo(f"[verify] [INFO] No {which} configured; nothing to run.")
        return

    root = gitutil.repo_root()
    for name, cmd in commands:
        click.echo(f"[verify] $ {cmd}")
        result = subprocess.run(cmd, shell=True, cwd=root)
        if result.returncode != 0:
            click.echo(f"[verify] [FAIL] {name} failed (exit {result.returncode}).")
            ctx.exit(result.returncode)
    click.echo(f"[verify] [OK] {', '.join(name for name, _ in commands)} passed.")


@commit_group.command("onboard")
@click.option("--force", is_flag=True, help="Overwrite an existing repository configuration.")
@click.option("--whitelist/--no-whitelist", default=None, help="Enable or disable identity whitelist check.")
@click.option("--timeline/--no-timeline", default=None, help="Enable or disable commit timestamp resolution.")
@click.option("--language", type=click.Choice(["ko", "en"]), default=None, help="Preferred commit language.")
@click.option("--style", default=None, help="Commit style (conventional, bracketed, ticket, custom).")
@click.option("--email", "emails", multiple=True, help="Allowed whitelist email(s). Can be specified multiple times.")
@click.option("--start", default=None, help="Timeline start time (HH:MM).")
@click.option("--end", default=None, help="Timeline end time (HH:MM).")
@click.option(
    "--hooks",
    "hooks_policy",
    type=click.Choice(HOOKS_POLICIES),
    default=None,
    help=(
        f"Git-hook policy for multi-commit splits. [default: {DEFAULT_HOOKS_POLICY}] "
        "run-all is reserved and fails as not implemented."
    ),
)
@click.option(
    "--test-cmd",
    default=None,
    help="Shell command that runs the repo's test suite (e.g. 'uv run pytest -q'). Empty skips test verification.",
)
@click.option(
    "--lint-cmd",
    default=None,
    help="Shell command that runs the repo's linter (e.g. 'ruff check'). Empty skips lint verification.",
)
@click.option(
    "--verify/--no-verify",
    "verify_enabled",
    default=None,
    help=(
        "Enable or disable running the verify commands. --no-verify keeps the "
        "commands on record but switches verification off (e.g. tests known-broken and mid-repair)."
    ),
)
def onboard(
    force: bool,
    whitelist: bool | None,
    timeline: bool | None,
    language: str | None,
    style: str | None,
    emails: tuple[str, ...],
    start: str | None,
    end: str | None,
    hooks_policy: str | None,
    test_cmd: str | None,
    lint_cmd: str | None,
    verify_enabled: bool | None,
) -> None:
    """Initialize or update repository commit configuration with auto-detected defaults."""
    existing = load_repo_config()
    if existing and not force:
        click.echo(f"[INFO] Repository is already onboarded: {existing.path}")
        click.echo("[INFO] Re-run with --force to overwrite, or use `agentkit commit config --set KEY=VALUE`.")
        return

    analysis = analyze_repo_history()

    # Determine final values
    final_whitelist_enabled = True if whitelist is None else whitelist
    final_emails = list(emails) if emails else ([analysis["primary_email"]] if analysis["primary_email"] else [])

    final_timeline_enabled = False if timeline is None else timeline
    final_lang = language or analysis["language"]
    final_style = style or analysis["style"]
    final_template = analysis["suggested_template"]

    final_hooks_policy = hooks_policy or DEFAULT_HOOKS_POLICY
    # The Choice already filters unknown values; this closes the reserved one.
    ensure_supported_hooks_policy(final_hooks_policy)

    target_path = repo_config_path()
    cfg = RepoConfig(
        path=target_path,
        whitelist=WhitelistConfig(
            enabled=final_whitelist_enabled,
            allowed_emails=final_emails,
        ),
        timeline=TimelineConfig(
            enabled=final_timeline_enabled,
            start=start or "19:00",
            end=end or "21:00",
        ),
        conventions=ConventionConfig(
            language=final_lang,
            style=final_style,
            template=final_template,
        ),
        hooks=HooksConfig(policy=final_hooks_policy),
        verify=VerifyConfig(
            enabled=True if verify_enabled is None else verify_enabled,
            test=test_cmd or "",
            lint=lint_cmd or "",
        ),
    )

    save_repo_config(cfg)
    click.echo(f"[SUCCESS] Initialized repository commit configuration at {target_path}")
    click.echo(
        f"  • Whitelist:   {'[ON]' if cfg.whitelist.enabled else '[OFF]'} ({', '.join(cfg.whitelist.allowed_emails)})"
    )
    click.echo(
        f"  • Timeline:    {'[ON]' if cfg.timeline.enabled else '[OFF]'} ({cfg.timeline.start}~{cfg.timeline.end} {cfg.timeline.timezone})"
    )
    click.echo(f"  • Language:    {cfg.conventions.language}")
    click.echo(f"  • Style:       {cfg.conventions.style}")
    click.echo(f"  • Hooks:       {cfg.hooks.policy}")
    click.echo(
        f"  • Verify:      {'[ON]' if cfg.verify.enabled else '[OFF]'} "
        f"test: {cfg.verify.test or '(none)'} | lint: {cfg.verify.lint or '(none)'}"
    )


def _set_nested(cfg: RepoConfig, key: str, value: str) -> None:
    parts = key.split(".", 1)
    if len(parts) == 1:
        if hasattr(cfg, key):
            setattr(cfg, key, _coerce(value))
        else:
            raise click.ClickException(f"Unknown config field: {key}")
        return

    section_name, prop_name = parts
    section = getattr(cfg, section_name, None)
    if section is None:
        raise click.ClickException(f"Unknown section: {section_name}")

    if hasattr(section, prop_name):
        current_val = getattr(section, prop_name)
        if isinstance(current_val, list):
            # comma-separated list
            setattr(section, prop_name, [item.strip() for item in value.split(",") if item.strip()])
        else:
            setattr(section, prop_name, _coerce(value, type(current_val)))
    else:
        raise click.ClickException(f"Unknown property: {prop_name} in section {section_name}")


def _coerce(value: str, target_type: type | None = None) -> Any:
    # Only a bool-typed field may word-match: without the type gate, string
    # values like "no" (a language) or int values like "0" turn into booleans.
    if target_type is bool:
        lowered = value.lower()
        if lowered not in ("true", "false", "yes", "no", "1", "0", "on", "off"):
            raise click.ClickException(f"Expected a boolean value, got: {value}")
        return lowered in ("true", "yes", "1", "on")
    if target_type is int:
        return int(value)
    return value
