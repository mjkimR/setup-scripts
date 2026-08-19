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

from agentkit.errors import AgentkitError, ConfigError, ExitCode, PreflightError
from agentkit.handoff.polish import run_polish

pytestmark = pytest.mark.integration


@pytest.fixture
def committed_doc(repo: Path):
    """A tracked Markdown file with a committed baseline."""

    def make(name: str = "docs/guide.md", content: str = "# Guide\n\n원래 문단입니다\n") -> Path:
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
    doc.write_text("# Guide\n\n수정된 문단입니다\n", encoding="utf-8")
    pending_file("new-doc.md", "# New\n\n새 문서입니다\n")
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
    doc.write_text("# Guide\n\n수정했습니다\n", encoding="utf-8")
    stub_agy.mode("polish")

    client = AgyClient(executable=stub_agy.client.executable, mode="accept-edits")
    run_polish(client=client, cwd=repo)

    assert stub_agy.calls()[0]["mode_flag"] == "accept-edits"


def test_targets_are_staged_so_git_restore_undoes_only_the_polish(repo, granted, stub_agy, committed_doc):
    doc = committed_doc()
    user_version = "# Guide\n\n사용자가 고친 문단입니다\n"
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
    doc.write_text("# Guide\n\n이미 자연스럽습니다\n", encoding="utf-8")
    stub_agy.mode("polish-clean")

    result = run(repo, stub_agy)

    assert result.exit_code == ExitCode.OK
    assert result.polished == []
    assert result.clean == ["docs/guide.md"]


def test_a_half_done_polish_is_incomplete(repo, granted, stub_agy, committed_doc, pending_file):
    doc = committed_doc()
    doc.write_text("# Guide\n\n수정했습니다\n", encoding="utf-8")
    pending_file("second.md", "# Second\n\n두 번째입니다\n")
    stub_agy.mode("polish-partial")

    result = run(repo, stub_agy)

    assert result.exit_code == ExitCode.INCOMPLETE
    assert len(result.polished) == 1
    assert len(result.unaccounted) == 1


def test_a_polished_mark_without_an_edit_is_not_believed(repo, granted, stub_agy, committed_doc, capsys):
    doc = committed_doc()
    doc.write_text("# Guide\n\n수정했습니다\n", encoding="utf-8")
    stub_agy.mode("polish-liar")

    result = run(repo, stub_agy)

    reported = capsys.readouterr().err
    assert result.exit_code == ExitCode.FAILED
    assert result.polished == []
    assert "(NO_FILES_POLISHED)" in reported


def test_a_denied_run_is_not_mistaken_for_a_clean_result(repo, granted, stub_agy, committed_doc, capsys):
    doc = committed_doc()
    doc.write_text("# Guide\n\n수정했습니다\n", encoding="utf-8")
    stub_agy.mode("none")

    result = run(repo, stub_agy)

    reported = capsys.readouterr().err
    assert result.exit_code == ExitCode.FAILED
    assert "no polished result" in reported
    assert "(AGY_PERMISSION_DENIED)" in reported


def test_a_spent_quota_defers_because_nothing_was_touched(repo, granted, stub_agy, committed_doc, capsys):
    doc = committed_doc()
    doc.write_text("# Guide\n\n수정했습니다\n", encoding="utf-8")
    stub_agy.mode("quota")

    result = run(repo, stub_agy)

    reported = capsys.readouterr().err
    assert result.exit_code == ExitCode.FAILED
    assert "(QUOTA_EXHAUSTED)" in reported
    assert "[ACTION] DEFER" in reported


def test_instructions_reach_the_prompt(repo, granted, stub_agy, committed_doc):
    doc = committed_doc()
    doc.write_text("# Guide\n\n수정했습니다\n", encoding="utf-8")
    stub_agy.mode("polish")

    run(repo, stub_agy, instructions=("합쇼체를 해요체로 바꿔줘",))

    prompt = stub_agy.calls()[0]["prompt"]
    assert "Caller instructions" in prompt
    assert "1. 합쇼체를 해요체로 바꿔줘" in prompt
    assert "outrank the style pack and the default style rules" in prompt


def test_without_instructions_the_prompt_stays_as_before(repo, granted, stub_agy, committed_doc):
    doc = committed_doc()
    doc.write_text("# Guide\n\n수정했습니다\n", encoding="utf-8")
    stub_agy.mode("polish")

    run(repo, stub_agy)

    assert "Caller instructions" not in stub_agy.calls()[0]["prompt"]


def test_base_widens_the_target_set_to_committed_changes(repo, granted, stub_agy, committed_doc):
    committed_doc()  # baseline commit
    base = git(repo, "rev-parse", "HEAD").strip()
    doc2 = committed_doc("docs/second.md", "# Second\n\n베이스 이후 커밋한 문서입니다\n")
    assert doc2.is_file()
    stub_agy.mode("polish")

    result = run(repo, stub_agy, base=base)

    # The tree is clean, but the doc committed after base is still a target.
    assert result.polished == ["docs/second.md"]
    assert f"git diff --cached {base}" in stub_agy.calls()[0]["prompt"]


def test_an_unknown_base_is_refused_before_any_call(repo, granted, stub_agy, committed_doc):
    doc = committed_doc()
    doc.write_text("# Guide\n\n수정했습니다\n", encoding="utf-8")

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
    original = "# Note\n\n번역투 문장입니다\n"
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
    doc.write_text("# Guide\n\n수정했습니다\n", encoding="utf-8")

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
    doc.write_text("# Guide\n\n수정했습니다\n", encoding="utf-8")
    stub_agy.mode("polish-delete")

    result = run(repo, stub_agy)

    reported = capsys.readouterr().err
    assert result.exit_code == ExitCode.FAILED
    assert result.polished == []
    assert "no longer exists" in reported
    assert "git restore docs/guide.md" in reported


def test_the_default_level_pack_rides_along_in_the_prompt(repo, granted, stub_agy, committed_doc):
    """The pack is inlined, not left for the receiver to fetch: a skill-directory
    read sits outside --add-dir, and a soft denial there would look like success."""
    doc = committed_doc()
    doc.write_text("# Guide\n\n수정했습니다\n", encoding="utf-8")
    stub_agy.mode("polish")

    run(repo, stub_agy)

    prompt = stub_agy.calls()[0]["prompt"]
    assert "[L3 담백한 합니다체]" in prompt  # the group its targets are listed under
    assert "===== 어체 L3 담백한 합니다체 · Korean =====" in prompt
    assert "## 쓰지 않는 표현" in prompt  # the pack body, not just its title
    assert "STYLE: <file> L3" in prompt  # the acknowledgement the contract asks for


def test_a_level_swaps_the_pack(repo, granted, stub_agy, committed_doc):
    doc = committed_doc()
    doc.write_text("# Guide\n\n수정했습니다\n", encoding="utf-8")
    stub_agy.mode("polish")

    result = run(repo, stub_agy, level=2)

    assert result.exit_code == ExitCode.OK
    prompt = stub_agy.calls()[0]["prompt"]
    assert "[L2 해라체 (평서형)]" in prompt
    assert "담백한 합니다체" not in prompt  # only the packs in play, never a menu
    assert "STYLE: <file> L2" in prompt


def test_an_unknown_level_is_refused_before_any_call(repo, granted, stub_agy, committed_doc):
    doc = committed_doc()
    doc.write_text("# Guide\n\n수정했습니다\n", encoding="utf-8")

    with pytest.raises(AgentkitError) as caught:
        run(repo, stub_agy, level=9)

    assert caught.value.exit_code == ExitCode.FAILED
    assert stub_agy.calls() == []
    # Refused before staging, so the user's tree is untouched.
    assert git(repo, "diff", "--cached", "--name-only").strip() == ""


def test_a_missing_pack_directory_stops_the_run(repo, granted, stub_agy, committed_doc, monkeypatch, tmp_path):
    from agentkit.handoff import style

    doc = committed_doc()
    doc.write_text("# Guide\n\n수정했습니다\n", encoding="utf-8")
    monkeypatch.setenv(style.STYLES_ENV, str(tmp_path / "nowhere"))
    monkeypatch.setattr(style, "_repo_styles_dir", lambda: tmp_path / "also-nowhere")
    monkeypatch.setattr(style, "_INSTALLED_DIRS", ())

    with pytest.raises(AgentkitError) as caught:
        run(repo, stub_agy)

    assert caught.value.exit_code == ExitCode.FAILED
    assert stub_agy.calls() == []


def test_a_style_mark_for_another_level_warns_but_keeps_the_polish(repo, granted, stub_agy, committed_doc, capsys):
    """The hashes prove the edits happened; only the diff shows the register.
    A wrong acknowledgement is the one failure they cannot see, so it warns."""
    doc = committed_doc()
    doc.write_text("# Guide\n\n수정했습니다\n", encoding="utf-8")
    stub_agy.mode("polish-wrong-style")

    result = run(repo, stub_agy, level=2)

    reported = capsys.readouterr().err
    assert result.exit_code == ExitCode.OK
    assert result.polished == ["docs/guide.md"]
    assert "applied a different 어체" in reported
    assert "git restore" in reported


def test_a_polish_without_a_style_mark_warns(repo, granted, stub_agy, committed_doc, capsys):
    doc = committed_doc()
    doc.write_text("# Guide\n\n수정했습니다\n", encoding="utf-8")
    stub_agy.mode("polish-no-style")

    result = run(repo, stub_agy)

    reported = capsys.readouterr().err
    assert result.exit_code == ExitCode.OK
    assert "without a STYLE line" in reported


def test_a_level_on_changed_regions_says_the_rest_of_the_file_keeps_its_register(
    repo, granted, stub_agy, committed_doc, capsys
):
    doc = committed_doc()
    doc.write_text("# Guide\n\n수정했습니다\n", encoding="utf-8")
    stub_agy.mode("polish")

    run(repo, stub_agy, level=5)

    reported = capsys.readouterr().out
    assert "changed regions only" in reported
    assert "L5 해요체" in reported


def test_an_out_of_range_level_is_a_usage_error():
    from click.testing import CliRunner

    from agentkit.cli import cli

    result = CliRunner().invoke(cli, ["handoff", "polish", "--level", "9"])

    assert result.exit_code == int(ExitCode.USAGE)


def test_a_changed_file_with_no_korean_prose_never_reaches_agy(
    repo, granted, stub_agy, committed_doc, pending_file, capsys
):
    """A changed-file sweep picks up whatever is in the tree. Sending an
    English-only doc spends quota to be told CLEAN, so it is dropped here."""
    doc = committed_doc()
    doc.write_text("# Guide\n\n수정했습니다\n", encoding="utf-8")
    pending_file("CHANGELOG.md", "# Changelog\n\nEnglish release notes only.\n")
    stub_agy.mode("polish")

    result = run(repo, stub_agy)

    reported = capsys.readouterr().out
    assert result.polished == ["docs/guide.md"]
    assert "CHANGELOG.md" not in stub_agy.calls()[0]["prompt"]
    assert "no Korean prose" in reported


def test_a_sweep_with_nothing_korean_in_it_costs_nothing(repo, granted, stub_agy, pending_file):
    pending_file("CHANGELOG.md", "# Changelog\n\nEnglish only.\n")
    pending_file("README.md", "# Readme\n\nAlso English.\n")

    result = run(repo, stub_agy)

    assert result.exit_code == ExitCode.OK
    assert stub_agy.calls() == []


def test_korean_inside_a_code_block_does_not_make_a_file_a_target(repo, granted, stub_agy, pending_file):
    """The polisher edits prose only, so Korean that only appears in a fenced
    example is not work it can do."""
    pending_file("guide.md", "# Guide\n\nEnglish text.\n\n```\nprint('한글')\n```\n")

    result = run(repo, stub_agy)

    assert result.exit_code == ExitCode.OK
    assert stub_agy.calls() == []


def test_an_explicitly_named_file_is_sent_despite_the_filter(repo, granted, stub_agy, pending_file, capsys):
    """The filter guesses at intent; an explicit path states it."""
    path = pending_file("notes.md", "# Notes\n\nEnglish only.\n")
    stub_agy.mode("polish")

    result = run(repo, stub_agy, paths=(path,))

    reported = capsys.readouterr().err
    assert result.polished == ["notes.md"]
    assert "you named it" in reported


def test_the_language_reaches_the_prompt(repo, granted, stub_agy, committed_doc):
    doc = committed_doc()
    doc.write_text("# Guide\n\n수정했습니다\n", encoding="utf-8")
    stub_agy.mode("polish")

    run(repo, stub_agy)

    prompt = stub_agy.calls()[0]["prompt"]
    assert "The target language is Korean" in prompt
    assert "· Korean" in prompt


def test_a_language_without_packs_is_refused_before_any_call(repo, granted, stub_agy, committed_doc):
    doc = committed_doc()
    doc.write_text("# Guide\n\n수정했습니다\n", encoding="utf-8")

    with pytest.raises(AgentkitError) as caught:
        run(repo, stub_agy, language="en")

    assert caught.value.exit_code == ExitCode.FAILED
    assert stub_agy.calls() == []


@pytest.fixture
def level_map(repo: Path):
    """The repository's path→어체 map, next to the commit config in .git."""

    def write(levels: dict) -> Path:
        import json

        path = repo / ".git" / "agentkit-polish.json"
        path.write_text(json.dumps({"levels": levels}), encoding="utf-8")
        return path

    return write


def test_the_repo_map_gives_each_file_its_own_어체_in_one_run(
    repo, granted, stub_agy, committed_doc, pending_file, level_map, capsys
):
    """The reason the map exists: two runs cannot do this. The second sweep
    would find the first run's files still changed and re-register them."""
    level_map({"docs/decisions/**": 2, "*.md": 4})
    adr = committed_doc("docs/decisions/0001-choice.md", "# 결정\n\n원래 문단입니다\n")
    adr.write_text("# 결정\n\n고친 문단입니다\n", encoding="utf-8")
    pending_file("README.md", "# 리드미\n\n새 문단입니다\n")
    stub_agy.mode("polish")

    result = run(repo, stub_agy)

    prompt = stub_agy.calls()[0]["prompt"]
    assert sorted(result.polished) == ["README.md", "docs/decisions/0001-choice.md"]
    assert "[L2 해라체 (평서형)]\n- changed-regions :: docs/decisions/0001-choice.md" in prompt
    assert "[L4 합니다체 (완곡)]\n- changed-regions :: README.md" in prompt
    # Both packs ride along, in ladder order, and nothing else does.
    assert prompt.index("===== 어체 L2") < prompt.index("===== 어체 L4")
    assert "===== 어체 L3" not in prompt
    assert str(repo / ".git" / "agentkit-polish.json") in capsys.readouterr().out


def test_the_first_matching_pattern_wins(repo, granted, stub_agy, committed_doc, level_map):
    """Specific first, catch-all second — the order people write these in."""
    level_map({"docs/decisions/**": 2, "docs/**": 5})
    adr = committed_doc("docs/decisions/0001-choice.md", "# 결정\n\n원래 문단입니다\n")
    adr.write_text("# 결정\n\n고친 문단입니다\n", encoding="utf-8")
    stub_agy.mode("polish")

    run(repo, stub_agy)

    assert "[L2 해라체 (평서형)]" in stub_agy.calls()[0]["prompt"]


def test_an_explicit_level_overrides_the_map(repo, granted, stub_agy, committed_doc, level_map):
    level_map({"docs/**": 1})
    doc = committed_doc()
    doc.write_text("# Guide\n\n수정했습니다\n", encoding="utf-8")
    stub_agy.mode("polish")

    run(repo, stub_agy, level=5)

    prompt = stub_agy.calls()[0]["prompt"]
    assert "[L5 해요체 (정중·친절)]" in prompt
    assert "개조식" not in prompt


def test_a_map_naming_a_level_that_does_not_exist_stops_the_run(repo, granted, stub_agy, committed_doc, level_map):
    level_map({"docs/**": 9})
    doc = committed_doc()
    doc.write_text("# Guide\n\n수정했습니다\n", encoding="utf-8")

    with pytest.raises(AgentkitError) as caught:
        run(repo, stub_agy)

    assert caught.value.exit_code == ExitCode.INCOMPLETE
    assert stub_agy.calls() == []


def test_a_broken_map_is_not_silently_ignored(repo, granted, stub_agy, committed_doc):
    """A typo in the map must not fall back to the default 어체 — that is the
    one outcome the user would never notice."""
    doc = committed_doc()
    doc.write_text("# Guide\n\n수정했습니다\n", encoding="utf-8")
    (repo / ".git" / "agentkit-polish.json").write_text("{levels: oops}", encoding="utf-8")

    with pytest.raises(AgentkitError):
        run(repo, stub_agy)

    assert stub_agy.calls() == []


def test_per_file_style_marks_are_attributed_by_path(repo, granted, stub_agy):
    from agentkit.handoff.polish import PolishTarget, _parse_style_marks

    targets = [
        PolishTarget(path=repo / "a.md", display="a.md", scope="whole-file", rollback="index"),
        PolishTarget(path=repo / "b.md", display="b.md", scope="whole-file", rollback="index"),
    ]

    output = "STYLE: a.md L2\n- `STYLE: b.md` — L4 applied\nSTYLE: other.md L1\n"

    assert _parse_style_marks(output, targets) == {"a.md": "L2", "b.md": "L4"}
