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
from agentkit.errors import ExitCode, PreflightError
from agentkit.handoff import get_task, run_handoff

pytestmark = pytest.mark.integration

COMMIT = get_task("commit")
COMMIT_SAFE = get_task("commit-safe")


def run(task, repo: Path, stub_agy, **kwargs):
    return run_handoff(task, client=stub_agy.client, repo=repo, **kwargs)


def test_a_clean_tree_costs_nothing(repo, granted, stub_agy):
    result = run(COMMIT, repo, stub_agy)

    assert result.exit_code == ExitCode.OK
    assert stub_agy.calls() == []


def test_the_first_commit_in_an_empty_repository_is_counted(
    repo, granted, stub_agy, pending_file
):
    pending_file("a.txt")

    result = run(COMMIT, repo, stub_agy)

    # Regression: `git rev-parse HEAD` on an unborn branch prints the literal
    # "HEAD", which used to make the range HEAD..<sha> and the count zero.
    assert result.exit_code == ExitCode.OK
    assert len(result.commits) == 1
    assert not result.remaining


def test_the_prompt_pins_the_repository_and_the_skill(
    repo, granted, stub_agy, pending_file
):
    pending_file("a.txt")

    run(COMMIT, repo, stub_agy)

    call = stub_agy.calls()[0]
    assert call["prompt"].startswith("/git-commit")
    assert str(repo) in call["prompt"]
    # --add-dir is not optional: without it agy runs in whatever repository it
    # used last, and with commit rules granted that means commits in the wrong one.
    assert call["add_dir"] == str(repo)


def test_leftover_files_make_the_handoff_incomplete(
    repo, granted, stub_agy, pending_file
):
    pending_file("a.txt")
    pending_file("b.txt")
    stub_agy.mode("one")

    result = run(COMMIT, repo, stub_agy)

    assert result.exit_code == ExitCode.INCOMPLETE
    assert len(result.commits) == 1
    assert len(result.remaining) == 1


def test_a_denied_run_is_not_mistaken_for_success(
    repo, granted, stub_agy, pending_file, capsys
):
    pending_file("a.txt")
    stub_agy.mode("none")

    result = run(COMMIT, repo, stub_agy)

    assert result.exit_code == ExitCode.FAILED
    assert result.commits == []
    reported = capsys.readouterr()
    assert "HEAD did not move" in reported.err
    # The denied command is only ever named in agy's log file.
    assert "git ls-files --others" in reported.err


def test_an_authentication_failure_is_named(
    repo, granted, stub_agy, pending_file, capsys
):
    pending_file("a.txt")
    stub_agy.mode("auth")

    result = run(COMMIT, repo, stub_agy)

    assert result.exit_code == ExitCode.FAILED
    assert "authentication failure" in capsys.readouterr().err


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


def test_safe_mode_calls_agy_once_per_unit(
    repo, granted, stub_agy, pending_file, safe_setup
):
    pending_file("a.txt")
    pending_file("b.txt")
    pending_file("c.txt")
    stub_agy.mode("one")

    result = run(COMMIT_SAFE, repo, stub_agy)

    assert result.exit_code == ExitCode.OK
    assert result.units == 3
    assert len(stub_agy.calls()) == 3
    assert not result.remaining


def test_safe_mode_resolves_a_fresh_timestamp_per_unit(
    repo, granted, stub_agy, pending_file, safe_setup
):
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


def test_safe_mode_stamps_the_commits_it_creates(
    repo, granted, stub_agy, pending_file, safe_setup
):
    pending_file("a.txt")
    stub_agy.mode("one")

    run(COMMIT_SAFE, repo, stub_agy)

    stamped = stub_agy.calls()[0]["author_date"][:16]
    logged = gitutil.log("HEAD", "%ad", date_format="%Y-%m-%d %H:%M", cwd=repo)
    assert logged == [stamped]


def test_safe_mode_constrains_agy_to_one_unit(
    repo, granted, stub_agy, pending_file, safe_setup
):
    pending_file("a.txt")
    stub_agy.mode("one")

    run(COMMIT_SAFE, repo, stub_agy)

    assert "EXACTLY ONE atomic unit" in stub_agy.calls()[0]["prompt"]


def test_a_rejected_identity_spends_no_quota(
    repo, granted, stub_agy, pending_file, safe_setup
):
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


def test_the_loop_guard_stops_a_runaway_split(
    repo, granted, stub_agy, pending_file, safe_setup
):
    pending_file("a.txt")
    pending_file("b.txt")
    pending_file("c.txt")
    stub_agy.mode("one")

    result = run(COMMIT_SAFE, repo, stub_agy, max_units=2)

    assert result.exit_code == ExitCode.INCOMPLETE
    assert len(stub_agy.calls()) == 2
    assert result.remaining
