"""Tests for structured error types, action modes, and CLI error formatting."""

from __future__ import annotations

import click
import pytest
from click.testing import CliRunner

from agentkit.cli import ErrorHandlingGroup
from agentkit.errors import (
    ActionMode,
    Actor,
    Advisory,
    AgentkitError,
    AgyAuthError,
    AgyNotInstalledError,
    AgyPermissionError,
    ConfigError,
    ErrorCode,
    ExitCode,
    IdentityError,
    MaintenanceError,
    NotOnboardedError,
    PreflightError,
    QuotaError,
    Retry,
    SkillContractError,
    WhitelistError,
)


def test_exit_codes_retain_expected_integer_values():
    assert ExitCode.OK == 0
    assert ExitCode.FAILED == 1
    assert ExitCode.INCOMPLETE == 2
    assert ExitCode.USAGE == 64


def test_action_modes_are_strings():
    assert ActionMode.AUTO == "AUTO"
    assert ActionMode.INTERACTION == "INTERACTION"
    assert ActionMode.HALT == "HALT"
    assert ActionMode.MAINTENANCE == "MAINTENANCE"


def test_error_code_enumeration():
    assert ErrorCode.REPO_NOT_ONBOARDED == "REPO_NOT_ONBOARDED"
    assert ErrorCode.AGY_PERMISSION_DENIED == "AGY_PERMISSION_DENIED"
    assert ErrorCode.AGY_UNAUTHENTICATED == "AGY_UNAUTHENTICATED"
    assert ErrorCode.PARTIAL_COMMITS == "PARTIAL_COMMITS"
    assert ErrorCode.SKILL_CONTRACT_MISMATCH == "SKILL_CONTRACT_MISMATCH"
    assert ErrorCode.TOOL_INTERNAL_ERROR == "TOOL_INTERNAL_ERROR"


def test_agentkit_error_defaults_and_backward_compatibility():
    err = AgentkitError("Something broke", "Hint 1", "Hint 2")
    assert err.exit_code == ExitCode.FAILED
    assert err.code == ErrorCode.GENERAL_ERROR
    assert err.mode == ActionMode.HALT
    assert err.hints == ("Hint 1", "Hint 2")
    assert err.details == ["Hint 1", "Hint 2"]
    assert err.fix is None
    assert err.what_to_report is None
    assert err.target_files == []


def test_specialized_error_subclasses_have_appropriate_defaults():
    cfg_err = ConfigError("Config is broken")
    assert cfg_err.exit_code == ExitCode.INCOMPLETE
    assert cfg_err.code == ErrorCode.CONFIG_INVALID
    assert cfg_err.mode == ActionMode.INTERACTION

    not_onboarded = NotOnboardedError("Not onboarded")
    assert not_onboarded.exit_code == ExitCode.INCOMPLETE
    assert not_onboarded.code == ErrorCode.REPO_NOT_ONBOARDED
    assert not_onboarded.mode == ActionMode.INTERACTION

    id_err = IdentityError("Forbidden email")
    assert id_err.exit_code == ExitCode.FAILED
    assert id_err.code == ErrorCode.IDENTITY_REJECTED
    assert id_err.mode == ActionMode.INTERACTION

    perm_err = AgyPermissionError("Missing grants")
    assert perm_err.exit_code == ExitCode.FAILED
    assert perm_err.code == ErrorCode.AGY_PERMISSION_DENIED
    assert perm_err.mode == ActionMode.AUTO

    auth_err = AgyAuthError("Auth failed")
    assert auth_err.exit_code == ExitCode.FAILED
    assert auth_err.code == ErrorCode.AGY_UNAUTHENTICATED
    assert auth_err.mode == ActionMode.INTERACTION

    pre_err = PreflightError("Preflight failed")
    assert pre_err.exit_code == ExitCode.FAILED
    assert pre_err.code == ErrorCode.PREFLIGHT_FAILED
    assert pre_err.mode == ActionMode.HALT

    maint_err = MaintenanceError("Internal issue", target_files=["tools/agentkit/src/foo.py"])
    assert maint_err.exit_code == ExitCode.FAILED
    assert maint_err.code == ErrorCode.TOOL_INTERNAL_ERROR
    assert maint_err.mode == ActionMode.MAINTENANCE
    assert maint_err.target_files == ["tools/agentkit/src/foo.py"]

    skill_err = SkillContractError("Invalid prompt", target_files=["modules/agents/skills/foo/SKILL.md"])
    assert skill_err.exit_code == ExitCode.FAILED
    assert skill_err.code == ErrorCode.SKILL_CONTRACT_MISMATCH
    assert skill_err.mode == ActionMode.MAINTENANCE
    assert skill_err.target_files == ["modules/agents/skills/foo/SKILL.md"]


@pytest.mark.parametrize(
    ("actor", "retry", "guardrail", "expected"),
    [
        (Actor.TOOL, Retry.AFTER_FIX, False, ActionMode.AUTO),
        (Actor.USER, Retry.AFTER_FIX, False, ActionMode.INTERACTION),
        (Actor.DEVELOPER, Retry.AFTER_FIX, False, ActionMode.MAINTENANCE),
        (Actor.NONE, Retry.SAFE, False, ActionMode.DEFER),
        (Actor.NONE, Retry.UNSAFE, False, ActionMode.HALT),
        (Actor.USER, Retry.UNSAFE, False, ActionMode.HALT),
        # A guardrail outranks everything: never hand the agent a way around it.
        (Actor.USER, Retry.AFTER_FIX, True, ActionMode.BLOCKED),
        # Half-done work outranks the actor: acting would mean retrying.
        (Actor.TOOL, Retry.UNSAFE, False, ActionMode.HALT),
    ],
)
def test_mode_is_derived_from_actor_and_retry(actor, retry, guardrail, expected):
    advisory = Advisory(code=ErrorCode.GENERAL_ERROR, actor=actor, retry=retry, guardrail=guardrail)
    assert advisory.mode == expected


def test_no_error_code_is_declared_without_being_bound_to_anything():
    """A code nothing can emit is a promise the tool does not keep.

    Codes were once added ahead of the branches meant to raise them, and a
    caller has no way to tell a reserved name from one it might actually see.
    Bound means either an exception class defaults to it or some path passes it
    explicitly; if a new case turns up, add the code together with its branch.
    """
    from pathlib import Path

    from agentkit import errors as errors_module

    src = Path(errors_module.__file__).parent
    corpus = "\n".join(path.read_text(encoding="utf-8") for path in src.rglob("*.py"))

    orphans = sorted(code.name for code in ErrorCode if f"ErrorCode.{code.name}" not in corpus)
    assert not orphans, f"declared but unreachable: {', '.join(orphans)}"


def test_every_mode_carries_a_self_contained_directive():
    """A caller must be able to act on a block without any skill doc open.

    Skills used to restate the modes in a table; that table had to be copied
    into every skill and went stale the moment a mode was added. The text in
    this module is the only copy, so it has to say the whole thing — and a mode
    that has no text at all would raise KeyError while reporting some other
    failure, which is the worst possible moment to find out.
    """
    from agentkit.errors import _ACTION_TEXT

    assert set(_ACTION_TEXT) == set(ActionMode)
    for mode, text in _ACTION_TEXT.items():
        assert text.startswith(f"{mode.value} — ")
        # A bare label is a lookup key, not an instruction.
        assert len(text) > len(mode.value) + 40, f"{mode.value} reads as a label, not a directive"


def test_a_whitelist_rejection_is_blocked_and_offers_no_bypass():
    """The agent must not be handed a command that adds itself to the whitelist."""
    err = WhitelistError("email not allowed", details=["Allowed: someone@else.com"])

    assert err.mode == ActionMode.BLOCKED
    assert err.guardrail is True
    assert err.fix is None
    assert "BLOCKED" in "\n".join(err.advisory.lines())
    assert "[FIX]" not in "\n".join(err.advisory.lines())


def test_a_spent_quota_defers_rather_than_halting():
    err = QuotaError("rolling limit spent", retry_after="5h")

    assert err.mode == ActionMode.DEFER
    rendered = "\n".join(err.advisory.lines())
    assert "[ACTION] DEFER" in rendered
    assert "[WHEN]   Not before: 5h" in rendered


def test_an_uninstalled_agy_asks_the_user_rather_than_the_tool():
    err = AgyNotInstalledError("agy not found on PATH")

    assert err.code == ErrorCode.AGY_NOT_INSTALLED
    assert err.mode == ActionMode.INTERACTION
    assert err.fix is None, "installing a CLI is not a command this tool can hand over"


def test_cli_error_handling_group_formats_structured_output():
    @click.group(cls=ErrorHandlingGroup)
    def test_cli():
        pass

    @test_cli.command("fail-auto")
    def fail_auto():
        raise AgyPermissionError(
            "agy is missing permissions",
            fix="agentkit agy grant",
            what_to_report="agy execution permissions are missing.",
            details=["command(git add) missing"],
        )

    @test_cli.command("fail-maint")
    def fail_maint():
        raise SkillContractError(
            "unrecognized flag in skill prompt",
            target_files=["modules/agents/skills/handoff-commit/SKILL.md"],
            fix="Edit SKILL.md to remove --invalid-flag",
            what_to_report="A skill definition error occurred. You may fix it directly in this session with user approval.",
        )

    @test_cli.command("fail-crash")
    def fail_crash():
        raise RuntimeError("database corrupted or unexpected NoneType")

    runner = CliRunner()

    # Test AUTO mode
    res_auto = runner.invoke(test_cli, ["fail-auto"])
    assert res_auto.exit_code == 1
    assert "[ERROR]  (AGY_PERMISSION_DENIED) agy is missing permissions" in res_auto.output
    assert "[ACTION] AUTO — " in res_auto.output
    assert "the only mode that authorizes a retry" in res_auto.output
    assert "[FIX]    agentkit agy grant" in res_auto.output
    assert "[REPORT] agy execution permissions are missing." in res_auto.output
    assert "[DETAIL] command(git add) missing" in res_auto.output

    # Test MAINTENANCE mode
    res_maint = runner.invoke(test_cli, ["fail-maint"])
    assert res_maint.exit_code == 1
    assert "[ERROR]  (SKILL_CONTRACT_MISMATCH) unrecognized flag in skill prompt" in res_maint.output
    assert "[ACTION] MAINTENANCE — " in res_maint.output
    assert "repairing the tool is a separate" in res_maint.output
    assert "[TARGET] modules/agents/skills/handoff-commit/SKILL.md" in res_maint.output
    assert "[FIX]    Edit SKILL.md to remove --invalid-flag" in res_maint.output

    # Test unhandled crash
    res_crash = runner.invoke(test_cli, ["fail-crash"])
    assert res_crash.exit_code == 1
    assert "[ERROR]  (TOOL_INTERNAL_ERROR) Unhandled exception in agentkit:" in res_crash.output
    assert "[ACTION] MAINTENANCE — " in res_crash.output
    assert "[TARGET] tools/agentkit/" in res_crash.output
    assert "Traceback:" in res_crash.output
    assert "RuntimeError: database corrupted" in res_crash.output


def test_click_control_flow_is_not_reported_as_a_crash():
    """click.exceptions.Exit is a RuntimeError; the catch-all must let it pass."""

    @click.group(cls=ErrorHandlingGroup)
    def test_cli():
        pass

    @test_cli.command("ok")
    @click.pass_context
    def ok(ctx):
        click.echo("committed 2 units")
        ctx.exit(int(ExitCode.OK))

    @test_cli.command("incomplete")
    @click.pass_context
    def incomplete(ctx):
        click.echo("uncommitted changes remain")
        ctx.exit(int(ExitCode.INCOMPLETE))

    runner = CliRunner()

    # A subcommand exiting via ctx.exit() — the handoff command's normal path.
    res_ok = runner.invoke(test_cli, ["ok"])
    assert res_ok.exit_code == ExitCode.OK
    assert "committed 2 units" in res_ok.output
    assert "TOOL_INTERNAL_ERROR" not in res_ok.output

    res_incomplete = runner.invoke(test_cli, ["incomplete"])
    assert res_incomplete.exit_code == ExitCode.INCOMPLETE
    assert "uncommitted changes remain" in res_incomplete.output
    assert "TOOL_INTERNAL_ERROR" not in res_incomplete.output

    # --help exits through the same path.
    res_help = runner.invoke(test_cli, ["ok", "--help"])
    assert res_help.exit_code == ExitCode.OK
    assert "Usage:" in res_help.output
    assert "TOOL_INTERNAL_ERROR" not in res_help.output


def test_usage_errors_keep_click_rendering_and_take_exit_code_64():
    @click.group(cls=ErrorHandlingGroup)
    def test_cli():
        pass

    @test_cli.command("ok")
    def ok():
        pass

    runner = CliRunner()

    res_flag = runner.invoke(test_cli, ["ok", "--bogus-flag"])
    assert res_flag.exit_code == ExitCode.USAGE
    assert "No such option" in res_flag.output
    assert "TOOL_INTERNAL_ERROR" not in res_flag.output
    assert "Traceback" not in res_flag.output

    res_cmd = runner.invoke(test_cli, ["no-such-command"])
    assert res_cmd.exit_code == ExitCode.USAGE
    assert "No such command" in res_cmd.output
    assert "TOOL_INTERNAL_ERROR" not in res_cmd.output
