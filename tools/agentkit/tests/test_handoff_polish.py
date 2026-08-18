"""The polish runner, driven end to end against a stub agy.

Same trust model as the commit runner: agy's exit status means nothing, so
these tests are mostly about what the runner concludes from file hashes and
the POLISHED/CLEAN marks when the stub cooperates, half-cooperates, or lies.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# conftest's _git carries GIT_CONFIG_GLOBAL=/dev/null, so a developer's real
# global config (gpgsign, hooksPath) can never break these repos.
from conftest import _git as git

from agentkit.errors import ConfigError, ExitCode, PreflightError
from agentkit.handoff.polish import run_polish

pytestmark = pytest.mark.integration


@pytest.fixture
def committed_doc(repo: Path):
    """A tracked Markdown file with a committed baseline."""

    def make(name: str = "docs/guide.md", content: str = "# Guide\n\noriginal paragraph\n") -> Path:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        git(repo, "add", "--", name)
        git(repo, "-c", "user.email=test@example.com", "-c", "user.name=test", "commit", "-qm", f"add {name}")
        return path

    return make


def run(repo: Path, stub_agy, **kwargs):
    return run_polish(client=stub_agy.client, cwd=repo, **kwargs)


def test_a_tree_without_changed_markdown_costs_nothing(repo, granted, stub_agy, committed_doc, pending_file):
    committed_doc()
    pending_file("notes.txt", "changed but not markdown")

    result = run(repo, stub_agy)

    assert result.exit_code == ExitCode.OK
    assert stub_agy.calls() == []


def test_changed_and_untracked_markdown_become_targets(repo, granted, stub_agy, committed_doc, pending_file):
    doc = committed_doc()
    doc.write_text("# Guide\n\nedited paragraph\n", encoding="utf-8")
    pending_file("new-doc.md", "# New\n")
    pending_file("code.py", "print()")  # never a target
    stub_agy.mode("polish")

    result = run(repo, stub_agy)

    assert result.exit_code == ExitCode.OK
    assert sorted(result.polished) == ["docs/guide.md", "new-doc.md"]
    prompt = stub_agy.calls()[0]["prompt"]
    assert prompt.startswith("/polish-doc")
    assert str(repo) in prompt
    assert "- changed-regions :: docs/guide.md" in prompt
    assert "- changed-regions :: new-doc.md" in prompt
    assert "code.py" not in prompt


def test_the_client_runs_in_accept_edits_mode_via_the_cli_path(repo, granted, stub_agy, committed_doc):
    """The runner itself takes any client; the mode ride-along is what makes
    headless edits land at all, so the flag has to reach the agy command line."""
    from agentkit.agy.client import AgyClient

    doc = committed_doc()
    doc.write_text("# Guide\n\nedited\n", encoding="utf-8")
    stub_agy.mode("polish")

    client = AgyClient(executable=stub_agy.client.executable, mode="accept-edits")
    run_polish(client=client, cwd=repo)

    assert stub_agy.calls()[0]["mode_flag"] == "accept-edits"


def test_targets_are_staged_so_git_restore_undoes_only_the_polish(repo, granted, stub_agy, committed_doc):
    doc = committed_doc()
    user_version = "# Guide\n\nedited paragraph\n"
    doc.write_text(user_version, encoding="utf-8")
    stub_agy.mode("polish")

    result = run(repo, stub_agy)

    assert result.exit_code == ExitCode.OK
    assert "polished" in doc.read_text(encoding="utf-8")
    git(repo, "restore", "--", "docs/guide.md")
    # The index holds the pre-polish state: the user's edit survives the undo.
    assert doc.read_text(encoding="utf-8") == user_version


def test_every_file_marked_clean_is_a_success(repo, granted, stub_agy, committed_doc):
    doc = committed_doc()
    doc.write_text("# Guide\n\nalready natural\n", encoding="utf-8")
    stub_agy.mode("polish-clean")

    result = run(repo, stub_agy)

    assert result.exit_code == ExitCode.OK
    assert result.polished == []
    assert result.clean == ["docs/guide.md"]


def test_a_half_done_polish_is_incomplete(repo, granted, stub_agy, committed_doc, pending_file):
    doc = committed_doc()
    doc.write_text("# Guide\n\nedited\n", encoding="utf-8")
    pending_file("second.md", "# Second\n")
    stub_agy.mode("polish-partial")

    result = run(repo, stub_agy)

    assert result.exit_code == ExitCode.INCOMPLETE
    assert len(result.polished) == 1
    assert len(result.unaccounted) == 1


def test_a_polished_mark_without_an_edit_is_not_believed(repo, granted, stub_agy, committed_doc, capsys):
    doc = committed_doc()
    doc.write_text("# Guide\n\nedited\n", encoding="utf-8")
    stub_agy.mode("polish-liar")

    result = run(repo, stub_agy)

    reported = capsys.readouterr().err
    assert result.exit_code == ExitCode.FAILED
    assert result.polished == []
    assert "(NO_FILES_POLISHED)" in reported


def test_a_denied_run_is_not_mistaken_for_a_clean_result(repo, granted, stub_agy, committed_doc, capsys):
    doc = committed_doc()
    doc.write_text("# Guide\n\nedited\n", encoding="utf-8")
    stub_agy.mode("none")

    result = run(repo, stub_agy)

    reported = capsys.readouterr().err
    assert result.exit_code == ExitCode.FAILED
    assert "no polished result" in reported
    assert "(AGY_PERMISSION_DENIED)" in reported


def test_a_spent_quota_defers_because_nothing_was_touched(repo, granted, stub_agy, committed_doc, capsys):
    doc = committed_doc()
    doc.write_text("# Guide\n\nedited\n", encoding="utf-8")
    stub_agy.mode("quota")

    result = run(repo, stub_agy)

    reported = capsys.readouterr().err
    assert result.exit_code == ExitCode.FAILED
    assert "(QUOTA_EXHAUSTED)" in reported
    assert "[ACTION] DEFER" in reported


def test_instructions_reach_the_prompt(repo, granted, stub_agy, committed_doc):
    doc = committed_doc()
    doc.write_text("# Guide\n\nedited\n", encoding="utf-8")
    stub_agy.mode("polish")

    run(repo, stub_agy, instructions=("합쇼체를 해요체로 바꿔줘",))

    prompt = stub_agy.calls()[0]["prompt"]
    assert "Caller instructions" in prompt
    assert "1. 합쇼체를 해요체로 바꿔줘" in prompt
    assert "override the default style rules" in prompt


def test_without_instructions_the_prompt_stays_as_before(repo, granted, stub_agy, committed_doc):
    doc = committed_doc()
    doc.write_text("# Guide\n\nedited\n", encoding="utf-8")
    stub_agy.mode("polish")

    run(repo, stub_agy)

    assert "Caller instructions" not in stub_agy.calls()[0]["prompt"]


def test_base_widens_the_target_set_to_committed_changes(repo, granted, stub_agy, committed_doc):
    committed_doc()  # baseline commit
    base = git(repo, "rev-parse", "HEAD").strip()
    doc2 = committed_doc("docs/second.md", "# Second\n\ncommitted after base\n")
    assert doc2.is_file()
    stub_agy.mode("polish")

    result = run(repo, stub_agy, base=base)

    # The tree is clean, but the doc committed after base is still a target.
    assert result.polished == ["docs/second.md"]
    assert f"git diff --cached {base}" in stub_agy.calls()[0]["prompt"]


def test_an_unknown_base_is_refused_before_any_call(repo, granted, stub_agy, committed_doc):
    doc = committed_doc()
    doc.write_text("# Guide\n\nedited\n", encoding="utf-8")

    with pytest.raises(ConfigError) as caught:
        run(repo, stub_agy, base="no-such-ref")

    # Exit 1, never 2: the exit-code contract reserves 2 for runs that
    # polished some files, and a refusal that touched nothing must not
    # masquerade as half-done work.
    assert caught.value.exit_code == ExitCode.FAILED
    assert stub_agy.calls() == []


def test_base_and_explicit_paths_do_not_combine(repo, granted, stub_agy, committed_doc):
    doc = committed_doc()

    with pytest.raises(ConfigError):
        run(repo, stub_agy, paths=(doc,), base="HEAD~1")

    assert stub_agy.calls() == []


def test_an_explicit_path_is_polished_whole(repo, granted, stub_agy, committed_doc):
    doc = committed_doc()  # clean tree: diff mode would find nothing
    stub_agy.mode("polish")

    result = run(repo, stub_agy, paths=(doc,))

    assert result.exit_code == ExitCode.OK
    assert result.polished == ["docs/guide.md"]
    assert "- whole-file :: docs/guide.md" in stub_agy.calls()[0]["prompt"]


def test_an_explicit_non_markdown_path_is_refused(repo, granted, stub_agy, pending_file):
    path = pending_file("script.py", "print()")

    with pytest.raises(ConfigError):
        run(repo, stub_agy, paths=(path,))

    assert stub_agy.calls() == []


def test_a_file_outside_the_repo_gets_a_backup_and_an_add_dir(repo, granted, stub_agy, tmp_path, committed_doc):
    committed_doc()  # give the repo a HEAD so staging paths behave
    outside = tmp_path / "elsewhere" / "note.md"
    outside.parent.mkdir(parents=True)
    original = "# Note\n\ntranslationese here\n"
    outside.write_text(original, encoding="utf-8")
    stub_agy.mode("polish")

    result = run(repo, stub_agy, paths=(outside,))

    assert result.exit_code == ExitCode.OK
    assert result.polished == [str(outside)]
    assert result.backup_dir is not None
    backups = list(result.backup_dir.iterdir())
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == original
    call = stub_agy.calls()[0]
    assert call["add_dir"] == str(repo)
    assert str(outside.parent) in call["add_dirs"]


def test_missing_the_diff_grant_aborts_before_any_call(repo, stub_agy, committed_doc, tmp_path, monkeypatch):
    from agentkit.agy import permissions

    monkeypatch.setattr(permissions, "SETTINGS_PATH", tmp_path / "absent.json")
    monkeypatch.setattr(permissions, "CONFIG_PATH", tmp_path / "absent2.json")
    doc = committed_doc()
    doc.write_text("# Guide\n\nedited\n", encoding="utf-8")

    with pytest.raises(PreflightError) as caught:
        run(repo, stub_agy)

    assert "command(git diff)" in str(caught.value)
    assert stub_agy.calls() == []


def test_an_explicit_whole_file_run_needs_no_git_grant(repo, stub_agy, committed_doc, tmp_path, monkeypatch):
    """Whole-file targets never read a diff, so an empty allow-list must not
    block them — the only permission that matters is the edit mode."""
    from agentkit.agy import permissions

    monkeypatch.setattr(permissions, "SETTINGS_PATH", tmp_path / "absent.json")
    monkeypatch.setattr(permissions, "CONFIG_PATH", tmp_path / "absent2.json")
    doc = committed_doc()
    stub_agy.mode("polish")

    result = run(repo, stub_agy, paths=(doc,))

    assert result.exit_code == ExitCode.OK


def test_a_malformed_instruction_is_a_usage_error():
    from click.testing import CliRunner

    from agentkit.cli import cli

    result = CliRunner().invoke(cli, ["handoff", "polish", "--instruction", "line one\nline two"])

    assert result.exit_code == int(ExitCode.USAGE)


def test_korean_named_files_are_found_despite_quotepath(repo, granted, stub_agy, committed_doc, pending_file):
    """git's default core.quotepath octal-escapes non-ASCII names in line
    output; the -z parsing must keep Korean-named docs — the whole point of
    this feature — in the target set."""
    doc = committed_doc("docs/가이드.md", "# 가이드\n\n원본 문단\n")
    doc.write_text("# 가이드\n\n수정된 문단\n", encoding="utf-8")
    pending_file("새문서.md", "# 새 문서\n")
    stub_agy.mode("polish")

    result = run(repo, stub_agy)

    assert result.exit_code == ExitCode.OK
    assert sorted(result.polished) == ["docs/가이드.md", "새문서.md"]


def test_decorated_mark_lines_still_count(repo, granted, stub_agy, committed_doc):
    """Receivers decorate contract lines despite instructions; a backticked
    or annotated mark must not fail an otherwise good run."""
    from agentkit.handoff.polish import PolishTarget, _parse_marks

    target = PolishTarget(
        path=repo / "docs" / "guide.md", display="docs/guide.md", scope="whole-file", rollback="index"
    )

    output = "All done!\nPOLISHED: docs/guide.md — fixed 3 sentences\n"
    assert _parse_marks(output, [target]) == {"docs/guide.md": "POLISHED"}

    output = "- CLEAN: `docs/guide.md` (no changes needed)\n"
    assert _parse_marks(output, [target]) == {"docs/guide.md": "CLEAN"}


def test_a_mark_for_a_different_file_is_not_attributed(repo, granted, stub_agy):
    """No basename fallback: a CLEAN mark has no hash backstop, so a mark for
    some other README the receiver browsed must not clear the real target."""
    from agentkit.handoff.polish import PolishTarget, _parse_marks

    target = PolishTarget(
        path=repo / "docs" / "README.md", display="docs/README.md", scope="whole-file", rollback="index"
    )

    assert _parse_marks("CLEAN: README.md\n", [target]) == {}
    assert _parse_marks("CLEAN: other/docs/README.md\n", [target]) == {}
    # The absolute spelling of the actual target still counts.
    assert _parse_marks(f"CLEAN: {target.path}\n", [target]) == {"docs/README.md": "CLEAN"}


def test_a_deleted_target_is_reported_not_crashed(repo, granted, stub_agy, committed_doc, capsys):
    doc = committed_doc()
    doc.write_text("# Guide\n\nedited\n", encoding="utf-8")
    stub_agy.mode("polish-delete")

    result = run(repo, stub_agy)

    reported = capsys.readouterr().err
    assert result.exit_code == ExitCode.FAILED
    assert result.polished == []
    assert "no longer exists" in reported
    assert "git restore docs/guide.md" in reported
