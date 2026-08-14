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

    # Modify config
    res = runner.invoke(cli, ["commit", "config", "--set", "conventions.language=en"])
    assert res.exit_code == 0
    assert "Updated conventions.language = en" in res.output

    # Verify updated config
    loaded = load_repo_config(cwd=repo)
    assert loaded is not None
    assert loaded.conventions.language == "en"


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
    assert loaded.timeline.enabled is True
    assert loaded.timeline.start == "19:00"
    assert loaded.conventions.language == "ko"
