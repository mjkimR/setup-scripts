"""The 어체 packs themselves: shape, not prose.

The packs are prompt input, so what these tests guard is the contract a pack
must meet to be usable — every rung present, every axis declared, the sections
the polisher is told to follow, and the ❌/✅ pairs that carry the rule. Nobody
can test whether L4 reads warmer than L3; that is the reviewer's job.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agentkit.errors import ExitCode
from agentkit.handoff import style

REQUIRED_SECTIONS = ("## 종결", "## 쓰지 않는 표현", "## 부연", "## 혼용 문서", "## 예시")


@pytest.fixture(scope="module")
def packs() -> list[style.StylePack]:
    return style.load_all()


def test_every_rung_of_the_ladder_has_a_pack(packs):
    assert [pack.level for pack in packs] == list(style.LEVELS)
    assert [pack.name for pack in packs] == [f"L{level}" for level in style.LEVELS]


def test_the_default_level_exists(packs):
    assert style.DEFAULT_LEVEL in style.LEVELS
    assert style.load_pack(style.DEFAULT_LEVEL).ending == "hapnida"


def test_each_pack_declares_both_axes(packs):
    """The level is a preset over 종결형 and 친절도. Keeping the axes on every
    pack is what lets one be overridden later without redesigning the ladder."""
    for pack in packs:
        assert pack.ending in ("nominal", "haera", "hapnida", "haeyo"), pack.name
        assert pack.verbosity in ("minimal", "lean", "expanded"), pack.name


def test_each_pack_carries_the_sections_the_prompt_relies_on(packs):
    for pack in packs:
        for section in REQUIRED_SECTIONS:
            assert section in pack.body, f"{pack.name} is missing {section}"


def test_each_pack_shows_its_rule_as_before_and_after_pairs(packs):
    """Rule sentences alone get read as a suggestion; the pairs are what make
    the register stick, so a pack without them is not finished."""
    for pack in packs:
        assert pack.body.count("❌") >= 5, pack.name
        assert pack.body.count("❌") == pack.body.count("✅"), pack.name


def test_the_expanded_levels_forbid_inventing_content(packs):
    """L4 and L5 add 부연, which is the one instruction that could turn a
    copyedit into authorship. Each must say so in its own body."""
    for pack in packs:
        if pack.verbosity == "expanded":
            assert "지어내지 않는다" in pack.body or "새로 만들어 넣지 않는다" in pack.body, pack.name


def test_an_unknown_level_is_an_error():
    with pytest.raises(style.StylePackError) as caught:
        style.load_pack(9)

    assert caught.value.exit_code == ExitCode.FAILED


def test_a_pack_without_frontmatter_is_an_error(tmp_path: Path):
    (tmp_path / "ko").mkdir()
    (tmp_path / "ko" / "L3.md").write_text("## 종결\n\n합니다체.\n", encoding="utf-8")

    with pytest.raises(style.StylePackError) as caught:
        style.load_pack(3, directory=tmp_path)

    assert "frontmatter" in str(caught.value)


def test_a_pack_missing_an_axis_is_an_error(tmp_path: Path):
    (tmp_path / "ko").mkdir()
    (tmp_path / "ko" / "L3.md").write_text(
        "---\nname: L3\nlanguage: ko\nlabel: 담백한 합니다체\nsummary: 한 줄\n---\n\n## 종결\n",
        encoding="utf-8",
    )

    with pytest.raises(style.StylePackError) as caught:
        style.load_pack(3, directory=tmp_path)

    assert "ending" in str(caught.value)


def test_the_env_override_wins_over_the_shipped_packs(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(style.STYLES_ENV, str(tmp_path))
    assert style.styles_dir() == tmp_path


def test_a_missing_override_falls_through_to_the_shipped_packs(tmp_path: Path, monkeypatch):
    """An override pointing nowhere must not strand the run: the packs that
    ship with the skill are still there, and they are the source of truth."""
    monkeypatch.setenv(style.STYLES_ENV, str(tmp_path / "absent"))

    assert (style.styles_dir() / "ko" / "L3.md").is_file()


def test_every_pack_declares_the_language_it_is_filed_under(packs):
    for pack in packs:
        assert pack.language == "ko", pack.name
        assert pack.path.parent.name == pack.language, pack.name
        assert pack.language_name == "Korean"


def test_the_installed_languages_are_listed_from_the_packs():
    assert "ko" in style.languages()


def test_a_misfiled_pack_is_an_error(tmp_path: Path):
    """The directory decides which language a pack answers for; frontmatter
    that disagrees means one of the two is wrong, and guessing is worse."""
    (tmp_path / "en").mkdir()
    (tmp_path / "en" / "L3.md").write_text(
        "---\nname: L3\nlanguage: ko\nlabel: 담백한 합니다체\nending: hapnida\nverbosity: lean\nsummary: 한 줄\n---\n\n## 종결\n",
        encoding="utf-8",
    )

    with pytest.raises(style.StylePackError) as caught:
        style.load_pack(3, "en", directory=tmp_path)

    assert "misfiled" in str(caught.value.what_to_report)


def test_prose_detection_looks_at_prose_only():
    assert style.has_prose("# 가이드\n\n한국어 문장입니다.\n", "ko")
    assert not style.has_prose("# Guide\n\nEnglish only.\n", "ko")
    assert not style.has_prose("# Guide\n\nSee `한글` and https://example.com/한글\n", "ko")
    assert not style.has_prose("---\ntitle: 한글 제목\n---\n\nEnglish body.\n", "ko")


def test_an_unknown_language_is_never_filtered_out():
    """The filter decides whether a file is handed over at all. Without a
    detector, sending it costs a CLEAN mark; dropping it loses real work."""
    assert style.has_prose("English only.\n", "en")
