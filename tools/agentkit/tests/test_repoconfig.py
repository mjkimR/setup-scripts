"""Tests for per-repository commit configuration and git history analysis."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from agentkit import gitutil
from agentkit.cli import cli
from agentkit.repoconfig import (
    ConventionConfig,
    RepoConfig,
    TimelineConfig,
    WhitelistConfig,
    analyze_repo_history,
    load_repo_config,
    repo_config_path,
    save_repo_config,
)


def test_repo_config_roundtrip(repo: Path) -> None:
    path = repo_config_path(cwd=repo)
    assert not path.is_file()
    assert load_repo_config(cwd=repo) is None

    cfg = RepoConfig(
        path=path,
        whitelist=WhitelistConfig(enabled=True, allowed_emails=["dev@company.com"]),
        timeline=TimelineConfig(enabled=True, start="18:00", end="20:00", timezone="Asia/Seoul"),
        conventions=ConventionConfig(language="ko", style="conventional", template="<type>: <subject>"),
    )

    saved_path = save_repo_config(cfg, cwd=repo)
    assert saved_path == path
    assert path.is_file()

    loaded = load_repo_config(cwd=repo)
    assert loaded is not None
    assert loaded.whitelist.enabled is True
    assert loaded.whitelist.allowed_emails == ["dev@company.com"]
    assert loaded.timeline.start == "18:00"
    assert loaded.conventions.language == "ko"
    assert loaded.whitelist.allows("dev@company.com")
    assert not loaded.whitelist.allows("other@company.com")


def test_repo_config_whitelist_disabled(repo: Path) -> None:
    path = repo_config_path(cwd=repo)
    cfg = RepoConfig(
        path=path,
        whitelist=WhitelistConfig(enabled=False, allowed_emails=[]),
    )
    save_repo_config(cfg, cwd=repo)

    loaded = load_repo_config(cwd=repo)
    assert loaded is not None
    assert loaded.whitelist.enabled is False
    # When disabled, any email is allowed
    assert loaded.whitelist.allows("anyone@world.com")


def test_analyze_repo_history_korean_conventional(repo: Path) -> None:
    gitutil.run(["config", "user.name", "Tester"], cwd=repo)
    gitutil.run(["config", "user.email", "tester@domain.com"], cwd=repo)

    # Create several commits with Korean conventional commit messages
    for i, msg in enumerate(
        [
            "feat(auth): 로그인 API 추가",
            "fix(core): 세션 만료 버그 수정",
            "docs(readme): 설치 가이드 업데이트",
        ],
        start=1,
    ):
        f = repo / f"file{i}.txt"
        f.write_text(f"content {i}\n", encoding="utf-8")
        gitutil.run(["add", str(f)], cwd=repo)
        gitutil.run(["commit", "-m", msg], cwd=repo)

    analysis = analyze_repo_history(cwd=repo)
    assert analysis["primary_email"] == "tester@domain.com"
    assert analysis["language"] == "ko"
    assert analysis["style"] == "conventional"
    assert analysis["total_commits"] == 3
    assert len(analysis["sample_subjects"]) == 3


def test_analyze_repo_history_bracketed_english(repo: Path) -> None:
    gitutil.run(["config", "user.name", "Alice"], cwd=repo)
    gitutil.run(["config", "user.email", "alice@example.com"], cwd=repo)

    for i, msg in enumerate(
        [
            "[auth] Add token verification",
            "[core] Fix memory leak in cache",
            "[docs] Update architecture document",
        ],
        start=1,
    ):
        f = repo / f"test{i}.txt"
        f.write_text(f"data {i}\n", encoding="utf-8")
        gitutil.run(["add", str(f)], cwd=repo)
        gitutil.run(["commit", "-m", msg], cwd=repo)

    analysis = analyze_repo_history(cwd=repo)
    assert analysis["primary_email"] == "alice@example.com"
    assert analysis["language"] == "en"
    assert analysis["style"] == "bracketed"


def test_analyze_repo_history_empty_repo(repo: Path) -> None:
    analysis = analyze_repo_history(cwd=repo)
    assert analysis["language"] == "en"
    assert analysis["style"] == "conventional"
    assert analysis["total_commits"] == 0
    assert "Overview of intent or motivation" in analysis["suggested_template"]


def test_commit_cli_onboard_and_config(repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(repo)
    runner = CliRunner()

    # Initial state: no config
    res = runner.invoke(cli, ["commit", "config"])
    assert res.exit_code == 0
    assert "No repository commit config found" in res.output

    # Run onboard
    res = runner.invoke(cli, ["commit", "onboard", "--language", "ko", "--style", "conventional"])
    assert res.exit_code == 0
    assert "[SUCCESS] Initialized repository commit configuration" in res.output

    # Show config
    res = runner.invoke(cli, ["commit", "config"])
    assert res.exit_code == 0
    assert "Language:    ko" in res.output
    assert "Style:       conventional" in res.output
    assert "Timeline:    [OFF]" in res.output

    # Modify config
    res = runner.invoke(cli, ["commit", "config", "--set", "conventions.language=en"])
    assert res.exit_code == 0
    assert "Updated conventions.language = en" in res.output

    # Verify updated config
    loaded = load_repo_config(cwd=repo)
    assert loaded is not None
    assert loaded.conventions.language == "en"
    assert loaded.timeline.enabled is False


def test_repo_config_migration_and_backfill(repo: Path) -> None:
    path = repo_config_path(cwd=repo)
    # Write a sparse/legacy config without version or timeline
    legacy_json = '{"whitelist": {"enabled": true, "allowed_emails": ["legacy@dev.com"]}}\n'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(legacy_json, encoding="utf-8")

    loaded = load_repo_config(cwd=repo, auto_migrate=True)
    assert loaded is not None
    # Version should be backfilled
    assert loaded.version == 1
    # Whitelist is preserved
    assert loaded.whitelist.allowed_emails == ["legacy@dev.com"]
    # Missing timeline and conventions are filled with defaults
    assert loaded.timeline.enabled is False
    assert loaded.timeline.start == "19:00"
    assert loaded.conventions.language == "en"
    # Pre-hooks/verify configs get the safe defaults
    assert loaded.hooks.policy == "bypass-intermediate"
    assert loaded.verify.configured() == []


def test_verify_commands_roundtrip_and_report_configured(repo: Path) -> None:
    from agentkit.repoconfig import VerifyConfig

    cfg = RepoConfig(path=repo_config_path(cwd=repo), verify=VerifyConfig(test="uv run pytest -q"))
    save_repo_config(cfg, cwd=repo)

    loaded = load_repo_config(cwd=repo)
    assert loaded is not None
    assert loaded.verify.test == "uv run pytest -q"
    # Only the configured half shows up; the empty lint field is skipped.
    assert loaded.verify.configured() == [("test", "uv run pytest -q")]
    assert loaded.verify.active() == loaded.verify.configured()

    # The off switch empties active() but keeps the commands on record —
    # a repo mid-repair must not have to erase what it will want back.
    loaded.verify.enabled = False
    save_repo_config(loaded, cwd=repo)
    reloaded = load_repo_config(cwd=repo)
    assert reloaded is not None
    assert reloaded.verify.enabled is False
    assert reloaded.verify.configured() == [("test", "uv run pytest -q")]
    assert reloaded.verify.active() == []


def test_commit_verify_echoes_each_command_before_running(repo: Path, monkeypatch) -> None:
    """Transparency is the wrapper's contract: the exact command line must be
    printed, and the command must actually execute."""
    from agentkit.repoconfig import VerifyConfig

    marker = repo / "verify-ran.marker"
    cfg = RepoConfig(
        path=repo_config_path(cwd=repo),
        verify=VerifyConfig(test=f"touch {marker.name}", lint="true"),
    )
    save_repo_config(cfg, cwd=repo)
    monkeypatch.chdir(repo)

    res = CliRunner().invoke(cli, ["commit", "verify"])

    assert res.exit_code == 0
    assert f"[verify] $ touch {marker.name}" in res.output
    assert "[verify] $ true" in res.output
    assert "[OK] test, lint passed" in res.output
    assert marker.is_file()


def test_commit_verify_propagates_the_failing_exit_code(repo: Path, monkeypatch) -> None:
    from agentkit.repoconfig import VerifyConfig

    cfg = RepoConfig(
        path=repo_config_path(cwd=repo),
        verify=VerifyConfig(test="exit 7", lint="touch lint-ran.marker"),
    )
    save_repo_config(cfg, cwd=repo)
    monkeypatch.chdir(repo)

    res = CliRunner().invoke(cli, ["commit", "verify"])

    assert res.exit_code == 7
    assert "[FAIL] test failed (exit 7)" in res.output
    # Stops at the first failure; lint never ran.
    assert not (repo / "lint-ran.marker").is_file()


def test_commit_verify_respects_the_off_switch(repo: Path, monkeypatch) -> None:
    from agentkit.repoconfig import VerifyConfig

    cfg = RepoConfig(
        path=repo_config_path(cwd=repo),
        verify=VerifyConfig(enabled=False, test="touch should-not-exist.marker"),
    )
    save_repo_config(cfg, cwd=repo)
    monkeypatch.chdir(repo)

    res = CliRunner().invoke(cli, ["commit", "verify"])

    # Skipping is loud (printed) but successful (exit 0), and nothing runs.
    assert res.exit_code == 0
    assert "[SKIP]" in res.output
    assert not (repo / "should-not-exist.marker").is_file()


def test_commit_verify_only_filters_to_one_command(repo: Path, monkeypatch) -> None:
    from agentkit.repoconfig import VerifyConfig

    cfg = RepoConfig(
        path=repo_config_path(cwd=repo),
        verify=VerifyConfig(test="touch test-ran.marker", lint="touch lint-ran.marker"),
    )
    save_repo_config(cfg, cwd=repo)
    monkeypatch.chdir(repo)

    res = CliRunner().invoke(cli, ["commit", "verify", "--only", "lint"])

    assert res.exit_code == 0
    assert (repo / "lint-ran.marker").is_file()
    assert not (repo / "test-ran.marker").is_file()


def test_run_all_hooks_policy_is_refused_everywhere(repo: Path, monkeypatch) -> None:
    """The option is visible but closed: onboarding and --set both fail loudly,
    so the config file never ends up holding a policy the runner would reject."""
    monkeypatch.chdir(repo)
    runner = CliRunner()

    res = runner.invoke(cli, ["commit", "onboard", "--hooks", "run-all"])
    assert res.exit_code != 0
    assert "not implemented" in res.output
    assert load_repo_config(cwd=repo) is None

    res = runner.invoke(cli, ["commit", "onboard", "--test-cmd", "uv run pytest -q", "--lint-cmd", "ruff check"])
    assert res.exit_code == 0

    res = runner.invoke(cli, ["commit", "config", "--set", "hooks.policy=run-all"])
    assert res.exit_code != 0
    assert "not implemented" in res.output
    loaded = load_repo_config(cwd=repo)
    assert loaded is not None
    assert loaded.hooks.policy == "bypass-intermediate"
    assert loaded.verify.test == "uv run pytest -q"
    assert loaded.verify.lint == "ruff check"


def test_the_polish_level_map_is_optional(repo: Path) -> None:
    """Polishing works in any repository, onboarded or not, so an absent map
    is the normal case and must not raise."""
    from agentkit.repoconfig import load_polish_config

    config = load_polish_config(cwd=repo)

    assert config.levels == {}
    assert config.level_for("README.md") is None


def test_the_polish_level_map_matches_paths_gitignore_style(repo: Path) -> None:
    import json

    from agentkit.repoconfig import load_polish_config, polish_config_path

    polish_config_path(cwd=repo).write_text(
        json.dumps({"levels": {"docs/decisions/**": 2, "docs/*": 5, "*.md": 3}}),
        encoding="utf-8",
    )
    config = load_polish_config(cwd=repo)

    assert config.level_for("docs/decisions/0001-x.md") == 2  # ** crosses separators
    assert config.level_for("docs/guide.md") == 5  # * stops at one
    assert config.level_for("docs/nested/guide.md") == 3  # so this falls through
    assert config.level_for("README.md") == 3  # a bare pattern matches the basename
    assert config.level_for("notes.txt") is None


def test_a_polish_level_map_with_a_bad_value_is_refused(repo: Path) -> None:
    import json

    import pytest

    from agentkit.errors import ConfigError
    from agentkit.repoconfig import load_polish_config, polish_config_path

    polish_config_path(cwd=repo).write_text(json.dumps({"levels": {"*.md": "two"}}), encoding="utf-8")

    with pytest.raises(ConfigError):
        load_polish_config(cwd=repo)


def test_a_polish_level_map_is_checked_against_the_installed_levels(repo: Path) -> None:
    import json

    import pytest

    from agentkit.errors import ConfigError
    from agentkit.repoconfig import load_polish_config, polish_config_path

    polish_config_path(cwd=repo).write_text(json.dumps({"levels": {"*.md": 9}}), encoding="utf-8")

    with pytest.raises(ConfigError):
        load_polish_config(cwd=repo, valid_levels=(1, 2, 3, 4, 5))
