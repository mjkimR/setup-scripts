"""The handoff runner, driven end to end against a stub agy.

The runner's whole reason to exist is that it does not believe the delegated
CLI, so most of these tests are about what it concludes when the stub reports
success and nothing happened.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agentkit import gitutil
from agentkit.errors import ConfigError, ExitCode, PreflightError
from agentkit.handoff import get_task, run_handoff
from agentkit.repoconfig import RepoConfig, WhitelistConfig, load_repo_config, save_repo_config

pytestmark = pytest.mark.integration

COMMIT = get_task("commit")
COMMIT_SAFE = get_task("commit-safe")


@pytest.fixture(autouse=True)
def onboarded_repo(repo: Path) -> None:
    save_repo_config(
        RepoConfig(
            path=repo / ".git" / "agentkit-commit.json",
            whitelist=WhitelistConfig(enabled=True, allowed_emails=["test@example.com"]),
        ),
        cwd=repo,
    )


def run(task, repo: Path, stub_agy, **kwargs):
    return run_handoff(task, client=stub_agy.client, repo=repo, **kwargs)


def test_unonboarded_repo_raises_preflight_error(repo: Path, granted, stub_agy, pending_file):
    config_file = repo / ".git" / "agentkit-commit.json"
    if config_file.is_file():
        config_file.unlink()

    pending_file("a.txt")
    with pytest.raises(ConfigError) as exc_info:
        run(COMMIT, repo, stub_agy)

    assert exc_info.value.exit_code == ExitCode.INCOMPLETE
    assert "not onboarded" in str(exc_info.value)


def test_a_clean_tree_costs_nothing(repo, granted, stub_agy):
    result = run(COMMIT, repo, stub_agy)

    assert result.exit_code == ExitCode.OK
    assert stub_agy.calls() == []


def test_the_first_commit_in_an_empty_repository_is_counted(repo, granted, stub_agy, pending_file):
    pending_file("a.txt")

    result = run(COMMIT, repo, stub_agy)

    # Regression: `git rev-parse HEAD` on an unborn branch prints the literal
    # "HEAD", which used to make the range HEAD..<sha> and the count zero.
    assert result.exit_code == ExitCode.OK
    assert len(result.commits) == 1
    assert not result.remaining


def test_the_prompt_pins_the_repository_and_the_skill(repo, granted, stub_agy, pending_file):
    pending_file("a.txt")

    run(COMMIT, repo, stub_agy)

    call = stub_agy.calls()[0]
    assert call["prompt"].startswith("/git-commit")
    assert str(repo) in call["prompt"]
    # --add-dir is not optional: without it agy runs in whatever repository it
    # used last, and with commit rules granted that means commits in the wrong one.
    assert call["add_dir"] == str(repo)


def test_the_prompt_always_carries_the_grouping_rules(repo, granted, stub_agy, pending_file):
    pending_file("a.txt")

    run(COMMIT, repo, stub_agy)

    prompt = stub_agy.calls()[0]["prompt"]
    # The two standing rules from the spec update: whole files only, and no
    # effort spent keeping intermediate commits green.
    assert "Never split one file's" in prompt
    assert "do not need to keep tests or\n  the build green" in prompt
    assert "Never run tests" in prompt


def test_the_prompt_carries_the_hook_policy(repo, granted, stub_agy, pending_file):
    pending_file("a.txt")

    run(COMMIT, repo, stub_agy)

    prompt = stub_agy.calls()[0]["prompt"]
    assert "bypass-intermediate" in prompt
    assert "--no-verify" in prompt
    # The final commit must run hooks; only intermediate ones bypass.
    assert "plain `git commit`" in prompt


def test_a_hand_edited_run_all_policy_stops_the_preflight(repo, granted, stub_agy, pending_file):
    """The CLI refuses to set run-all, but the JSON is just a file — a
    hand-edited policy must fail loudly before any quota is spent."""
    cfg = load_repo_config(cwd=repo)
    cfg.hooks.policy = "run-all"
    save_repo_config(cfg, cwd=repo)
    pending_file("a.txt")

    with pytest.raises(ConfigError) as caught:
        run(COMMIT, repo, stub_agy)

    assert "not implemented" in str(caught.value)
    assert stub_agy.calls() == []


def test_missing_attestation_with_verify_commands_prints_a_nudge(repo, granted, stub_agy, pending_file, capsys):
    cfg = load_repo_config(cwd=repo)
    cfg.verify.test = "uv run pytest -q"
    save_repo_config(cfg, cwd=repo)
    pending_file("a.txt")

    result = run(COMMIT, repo, stub_agy)

    reported = capsys.readouterr()
    # A nudge, not a gate: the handoff still runs and succeeds.
    assert result.exit_code == ExitCode.OK
    assert "uv run pytest -q" in reported.out + reported.err


def test_an_attested_handoff_gets_no_nudge(repo, granted, stub_agy, pending_file, capsys):
    cfg = load_repo_config(cwd=repo)
    cfg.verify.test = "uv run pytest -q"
    save_repo_config(cfg, cwd=repo)
    pending_file("a.txt")

    run(COMMIT, repo, stub_agy, tests="passed")

    reported = capsys.readouterr()
    assert "verify commands" not in reported.out + reported.err


def test_a_disabled_verify_config_silences_the_nudge(repo, granted, stub_agy, pending_file, capsys):
    """verify.enabled=false is a deliberate opt-out (tests mid-repair);
    nagging about the attestation would contradict it."""
    cfg = load_repo_config(cwd=repo)
    cfg.verify.test = "uv run pytest -q"
    cfg.verify.enabled = False
    save_repo_config(cfg, cwd=repo)
    pending_file("a.txt")

    run(COMMIT, repo, stub_agy)

    reported = capsys.readouterr()
    assert "verify commands" not in reported.out + reported.err


def test_hints_and_attestation_reach_the_prompt(repo, granted, stub_agy, pending_file):
    pending_file("a.txt")

    run(
        COMMIT,
        repo,
        stub_agy,
        hints=("feat: add pagination", "docs: describe cursors"),
        tests="passed",
    )

    prompt = stub_agy.calls()[0]["prompt"]
    assert "Caller context" in prompt
    assert "1. feat: add pagination" in prompt
    assert "2. docs: describe cursors" in prompt
    # The boundary conditions ride along with the hints: advisory only, diff
    # wins, no padded commits, subjects are the receiver's to write.
    assert "not final subjects" in prompt
    assert "ground truth" in prompt
    assert "empty or padded commit" in prompt
    assert "it passed" in prompt
    assert "do not re-run" in prompt


def test_without_caller_flags_the_prompt_stays_as_before(repo, granted, stub_agy, pending_file):
    pending_file("a.txt")

    run(COMMIT, repo, stub_agy)

    assert "Caller context" not in stub_agy.calls()[0]["prompt"]


def test_a_failed_attestation_still_authorizes_the_commit(repo, granted, stub_agy, pending_file):
    pending_file("a.txt")

    run(COMMIT, repo, stub_agy, tests="failed")

    prompt = stub_agy.calls()[0]["prompt"]
    assert "failing on this tree" in prompt
    assert "not a reason to hold back" in prompt


@pytest.mark.parametrize(
    "argv",
    [
        ["handoff", "commit", "--hint", "line one\nline two"],
        ["handoff", "commit", "--hint", ""],
    ],
    ids=["multiline", "empty"],
)
def test_a_malformed_hint_is_a_usage_error(argv):
    """A bad hint means the calling skill built a bad command line: exit 64,
    refused at parse time, before any repo access or quota spend. Shape only —
    length and count are advisory, so only a broken line structure is refused."""
    from click.testing import CliRunner

    from agentkit.cli import cli

    result = CliRunner().invoke(cli, argv)

    assert result.exit_code == int(ExitCode.USAGE)


def test_a_hint_commit_count_mismatch_is_reported_on_success(repo, granted, stub_agy, pending_file, capsys):
    """Success drops agy's narration, so the runner's count note is the only
    surviving trace of a hint the diff did not support."""
    pending_file("a.txt")

    result = run(COMMIT, repo, stub_agy, hints=("feat: unit a", "feat: unit b", "feat: unit c"))

    reported = capsys.readouterr()
    assert result.exit_code == ExitCode.OK
    assert "3 hint(s), 1 commit(s)" in reported.out + reported.err
    assert "hints are advisory" in reported.out + reported.err


def test_matching_hint_and_commit_counts_stay_quiet(repo, granted, stub_agy, pending_file, capsys):
    pending_file("a.txt")

    result = run(COMMIT, repo, stub_agy, hints=("feat: the one unit",))

    reported = capsys.readouterr()
    assert result.exit_code == ExitCode.OK
    assert "hints are advisory" not in reported.out + reported.err


def test_hint_length_and_count_are_not_capped(repo, granted, stub_agy, pending_file):
    """Receiver-side quota is the cheap side of the handoff: a long memory of
    the work, or many units, must pass through rather than exit 64."""
    hints = tuple(f"unit {i}: " + "x" * 200 for i in range(12))
    pending_file("a.txt")

    run(COMMIT, repo, stub_agy, hints=hints)

    prompt = stub_agy.calls()[0]["prompt"]
    assert f"12. {hints[11]}" in prompt


def test_leftover_files_make_the_handoff_incomplete(repo, granted, stub_agy, pending_file):
    pending_file("a.txt")
    pending_file("b.txt")
    stub_agy.mode("one")

    result = run(COMMIT, repo, stub_agy)

    assert result.exit_code == ExitCode.INCOMPLETE
    assert len(result.commits) == 1
    assert len(result.remaining) == 1


def test_a_denied_run_is_not_mistaken_for_success(repo, granted, stub_agy, pending_file, capsys):
    pending_file("a.txt")
    stub_agy.mode("none")

    result = run(COMMIT, repo, stub_agy)

    assert result.exit_code == ExitCode.FAILED
    assert result.commits == []
    reported = capsys.readouterr()
    assert "HEAD did not move" in reported.err
    # The denied command is only ever named in agy's log file.
    assert "git ls-files --others" in reported.err


def test_an_out_of_scope_denial_is_a_prompt_bug_not_a_grant_problem(
    repo, granted, stub_agy, pending_file, capsys, monkeypatch
):
    """Seen live (2026-08-18): agy was denied `git show`, which no grant will
    ever cover, yet the advisory said `agentkit agy grant` — a fix that changes
    nothing and invites a retry loop against the same wall."""
    pending_file("a.txt")
    stub_agy.mode("none")
    monkeypatch.setenv("AGY_STUB_DENIED", "git show --stat d659451")

    result = run(COMMIT, repo, stub_agy)

    reported = capsys.readouterr().err
    assert result.exit_code == ExitCode.FAILED
    assert "outside the task's permitted set" in reported
    assert "Out of scope: git show --stat d659451" in reported
    assert "[ACTION] HALT" in reported
    # The one fix that cannot help must not be offered.
    assert "agentkit agy grant" not in reported


def test_a_piped_denial_is_a_prompt_bug_and_names_the_evidence(
    repo, granted, stub_agy, pending_file, capsys, monkeypatch, tmp_path
):
    """Seen live (2026-09-10): agy piped a permitted `git diff` into `grep` to read
    the import lines of a large diff; the pipeline was denied as a whole and the
    advisory blamed missing grants, naming no command, and left no log behind."""
    from agentkit.agy import client as client_module

    monkeypatch.setattr(client_module, "LOG_DIR", tmp_path / "logs")
    pending_file("a.txt")
    stub_agy.mode("none")
    monkeypatch.setenv("AGY_STUB_DENIED", 'git diff src/main.py | grep -E "^+(from|import)"')

    result = run(COMMIT, repo, stub_agy)

    reported = capsys.readouterr().err
    assert result.exit_code == ExitCode.FAILED
    assert "outside the task's permitted set" in reported
    assert 'Out of scope: git diff src/main.py | grep -E "^+(from|import)"' in reported
    assert "pipe or chain" in reported
    assert "Log: " in reported and (tmp_path / "logs").exists()
    assert "agentkit agy grant" not in reported
    # and the prompt now forbids the pipe up front
    assert "Never pipe or chain" in stub_agy.calls()[0]["prompt"]


def test_an_in_scope_denial_still_points_at_the_grant_fix(repo, granted, stub_agy, pending_file, capsys, monkeypatch):
    pending_file("a.txt")
    stub_agy.mode("none")
    monkeypatch.setenv("AGY_STUB_DENIED", "git ls-files --others")

    result = run(COMMIT, repo, stub_agy)

    reported = capsys.readouterr().err
    assert result.exit_code == ExitCode.FAILED
    assert "agentkit agy grant" in reported
    assert "outside the task's permitted set" not in reported


def test_an_authentication_failure_is_named(repo, granted, stub_agy, pending_file, capsys):
    pending_file("a.txt")
    stub_agy.mode("auth")

    result = run(COMMIT, repo, stub_agy)

    reported = capsys.readouterr().err
    assert result.exit_code == ExitCode.FAILED
    assert "authentication failure" in reported
    # The stub also says "timed out"; the specific cause has to win.
    assert "(AGY_UNAUTHENTICATED)" in reported
    assert "AGY_TIMEOUT" not in reported


def test_a_spent_quota_tells_the_caller_to_wait_rather_than_stop(repo, granted, stub_agy, pending_file, capsys):
    pending_file("a.txt")
    stub_agy.mode("quota")

    result = run(COMMIT, repo, stub_agy)

    reported = capsys.readouterr().err
    assert result.exit_code == ExitCode.FAILED
    assert "(QUOTA_EXHAUSTED)" in reported
    assert "[ACTION] DEFER" in reported
    assert "Not before:" in reported


def test_a_timeout_defers_only_while_nothing_was_committed(repo, granted, stub_agy, pending_file, capsys):
    pending_file("a.txt")
    stub_agy.mode("timeout")

    result = run(COMMIT, repo, stub_agy)

    reported = capsys.readouterr().err
    assert result.exit_code == ExitCode.FAILED
    assert result.commits == []
    assert "(AGY_TIMEOUT)" in reported
    assert "[ACTION] DEFER" in reported


@pytest.mark.parametrize("stub_mode", ["none", "auth", "quota", "timeout"])
def test_an_earlier_commit_downgrades_every_cause_to_halt(stub_mode, capsys):
    """Whatever stopped agy, half-done work makes acting on it the user's call.

    Only AUTO authorizes a retry, so no cause may reach AUTO/DEFER once an
    earlier unit has committed — otherwise the skill would be told to re-run a
    handoff that already changed the repository.
    """
    from agentkit.agy import AgyRun
    from agentkit.handoff.runner import HandoffResult, _report_nothing_happened
    from agentkit.ui import Reporter

    outputs = {
        "none": "a tool required the command permission, but headless mode cannot prompt",
        "auth": "authentication failed",
        "quota": "RESOURCE_EXHAUSTED: usage limit reached",
        "timeout": "deadline exceeded while generating the commit",
    }
    run_result = AgyRun(output=outputs[stub_mode], log="")
    already = HandoffResult(ExitCode.FAILED, units=2, commits=["abc1234 feat: earlier unit"])

    _report_nothing_happened(Reporter("handoff"), run_result, already, COMMIT_SAFE, verbose=True)

    reported = capsys.readouterr().err
    assert "[ACTION] HALT" in reported
    assert "[ACTION] AUTO" not in reported
    assert "[ACTION] DEFER" not in reported


def test_missing_grants_abort_before_any_call(repo, stub_agy, pending_file, tmp_path, monkeypatch):
    from agentkit.agy import permissions

    monkeypatch.setattr(permissions, "SETTINGS_PATH", tmp_path / "absent.json")
    monkeypatch.setattr(permissions, "CONFIG_PATH", tmp_path / "absent2.json")
    pending_file("a.txt")

    with pytest.raises(PreflightError) as caught:
        run(COMMIT, repo, stub_agy)

    assert "command(git add)" in str(caught.value)
    assert stub_agy.calls() == []


def test_an_unavailable_agy_is_reported(repo, granted, stub_agy, pending_file):
    from agentkit.agy.client import AgyClient

    pending_file("a.txt")

    with pytest.raises(PreflightError) as caught:
        run_handoff(COMMIT, client=AgyClient(executable="agy-does-not-exist"), repo=repo)

    assert "not found on PATH" in str(caught.value)


# --- safe variant ----------------------------------------------------------


def test_safe_mode_calls_agy_once_per_unit(repo, granted, stub_agy, pending_file, safe_setup):
    pending_file("a.txt")
    pending_file("b.txt")
    pending_file("c.txt")
    stub_agy.mode("one")

    result = run(COMMIT_SAFE, repo, stub_agy)

    assert result.exit_code == ExitCode.OK
    assert result.units == 3
    assert len(stub_agy.calls()) == 3
    assert not result.remaining


def test_safe_mode_resolves_a_fresh_timestamp_per_unit(repo, granted, stub_agy, pending_file, safe_setup):
    pending_file("a.txt")
    pending_file("b.txt")
    stub_agy.mode("one")

    run(COMMIT_SAFE, repo, stub_agy)

    dates = [call["author_date"] for call in stub_agy.calls()]
    assert all(dates), "every call must carry a resolved date"
    # A single batched call would stamp every commit identically, which is the
    # whole reason the safe variant loops.
    assert len(set(dates)) == len(dates)
    assert [call["committer_date"] for call in stub_agy.calls()] == dates


def test_safe_mode_stamps_the_commits_it_creates(repo, granted, stub_agy, pending_file, safe_setup):
    pending_file("a.txt")
    stub_agy.mode("one")

    run(COMMIT_SAFE, repo, stub_agy)

    stamped = stub_agy.calls()[0]["author_date"][:16]
    logged = gitutil.log("HEAD", "%ad", date_format="%Y-%m-%d %H:%M", cwd=repo)
    assert logged == [stamped]


def test_safe_mode_tells_each_unit_where_the_hints_stand(repo, granted, stub_agy, pending_file, safe_setup):
    """Each per-unit call is a fresh agy with no memory of the previous split;
    the prompt has to route it to the next hint via git log — naming the exact
    permitted command, because "check git log" alone sent agy to the denied
    `git show` and stalled the unit (seen live, 2026-08-18)."""
    pending_file("a.txt")
    pending_file("b.txt")
    stub_agy.mode("one")

    run(COMMIT_SAFE, repo, stub_agy, hints=("feat: unit a", "feat: unit b"))

    for call in stub_agy.calls():
        assert "first hint whose\n  work" in call["prompt"]
        assert "git log --oneline --name-only -20" in call["prompt"]
        assert "`git show` is denied" in call["prompt"]
        assert "1. feat: unit a" in call["prompt"]


def test_safe_mode_constrains_agy_to_one_unit(repo, granted, stub_agy, pending_file, safe_setup):
    pending_file("a.txt")
    stub_agy.mode("one")

    run(COMMIT_SAFE, repo, stub_agy)

    assert "EXACTLY ONE atomic unit" in stub_agy.calls()[0]["prompt"]


def test_plain_mode_still_enforces_the_whitelist(repo, granted, stub_agy, pending_file):
    """The whitelist is not a timeline feature: the plain task must check it too."""
    subprocess.run(
        ["git", "config", "user.email", "stranger@example.com"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )
    pending_file("a.txt")

    from agentkit.errors import IdentityError

    with pytest.raises(IdentityError):
        run(COMMIT, repo, stub_agy)

    assert stub_agy.calls() == []


def test_a_stall_after_earlier_commits_is_incomplete_not_failed(repo, granted, stub_agy, pending_file, safe_setup):
    """Exit 1 promises "nothing was committed"; a stalled unit 2 must not say that."""
    pending_file("a.txt")
    pending_file("b.txt")
    stub_agy.mode("first")

    result = run(COMMIT_SAFE, repo, stub_agy)

    assert result.exit_code == ExitCode.INCOMPLETE
    assert len(result.commits) == 1


def test_a_rejected_identity_spends_no_quota(repo, granted, stub_agy, pending_file, safe_setup):
    pending_file("a.txt")
    subprocess.run(
        ["git", "config", "user.email", "stranger@example.com"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )

    from agentkit.errors import IdentityError

    with pytest.raises(IdentityError):
        run(COMMIT_SAFE, repo, stub_agy)

    assert stub_agy.calls() == []


def test_the_loop_guard_stops_a_runaway_split(repo, granted, stub_agy, pending_file, safe_setup):
    pending_file("a.txt")
    pending_file("b.txt")
    pending_file("c.txt")
    stub_agy.mode("one")

    result = run(COMMIT_SAFE, repo, stub_agy, max_units=2)

    assert result.exit_code == ExitCode.INCOMPLETE
    assert len(stub_agy.calls()) == 2
    assert result.remaining
