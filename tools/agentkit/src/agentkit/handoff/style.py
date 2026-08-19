"""The 어체 ladder: five discrete style packs, addressed by level.

A level is an ordinal label for a fully specified pack, never a point on a
continuum — there is no 2.5, and nothing interpolates between rungs. Each pack
names its own 종결어미, its banned phrasings and its 부연 policy, and carries
the ❌/✅ pairs that make the rule stick. Rules that hold at every level
(번역투 제거, 피동, 명사화, 보호 대상) stay in the skill; only what actually
varies with register lives here.

Packs are filed by language, and a pack's language is also the polish run's
language filter: prose in any other language is left alone, and a document
with none of the target language in it never reaches the receiver at all.

The packs ship inside the `polish-doc` skill, because an interactive
`/polish-doc` run reads them itself. The headless path does not rely on that:
`polish_prompt` inlines the selected pack, since a skill-directory read sits
outside agy's `--add-dir` scope and a soft denial there would silently polish
at the default register and exit 0.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from ..errors import ExitCode, MaintenanceError

DEFAULT_LEVEL = 3  # matches the register the skill used before levels existed
DEFAULT_LANGUAGE = "ko"
LEVELS = (1, 2, 3, 4, 5)
STYLES_ENV = "AGENTKIT_POLISH_STYLES"

# Endonym-free English names, because they go into an English prompt.
LANGUAGE_NAMES = {"ko": "Korean"}

# What counts as prose in a language, for the pre-flight filter. A language
# with no detector here is never filtered: sending a file that needed nothing
# costs one CLEAN mark, while dropping one that needed work is silent damage.
_SCRIPTS = {"ko": re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣ]")}

# Prose only, same as the polisher's own remit: fenced code, inline code,
# frontmatter and URLs are stripped before the script test, so a Python file's
# worth of English inside a Korean doc cannot flip the verdict either way.
_CODE_FENCE = re.compile(r"^```.*?^```", re.DOTALL | re.MULTILINE)
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_URL = re.compile(r"https?://\S+")

_SKILL_RELATIVE = Path("modules/agents/skills/polish-doc/references/style")
_INSTALLED_DIRS = (Path.home() / ".gemini/config/skills/polish-doc/references/style",)
_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.DOTALL)


class StylePackError(MaintenanceError):
    """A style pack that cannot be found or read.

    Exit 1, not MaintenanceError's default: this command's exit-code contract
    reserves 2 for runs that polished some files and left others unaccounted,
    and a refusal that touched nothing must not read as half-done work.
    """

    exit_code = ExitCode.FAILED


@dataclass(frozen=True)
class StylePack:
    level: int
    language: str  # "ko"; also the language filter the run applies
    name: str  # "L2"
    label: str  # "해라체 (평서형)"
    ending: str  # 종결형 축: nominal | haera | hapnida | haeyo
    verbosity: str  # 친절도 축: minimal | lean | expanded
    summary: str  # one line; the only part that survives a body-less fallback
    body: str  # everything under the frontmatter, inlined into the prompt
    path: Path

    @property
    def title(self) -> str:
        return f"{self.name} {self.label}"

    @property
    def language_name(self) -> str:
        return LANGUAGE_NAMES.get(self.language, self.language)


def styles_dir(*, env: dict[str, str] | None = None) -> Path:
    """Locate the pack directory: env override, then repo, then installed skill."""
    environ = os.environ if env is None else env
    override = environ.get(STYLES_ENV)
    candidates = []
    if override:
        candidates.append(Path(override).expanduser())
    candidates.append(_repo_styles_dir())
    candidates.extend(_INSTALLED_DIRS)

    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise StylePackError(
        "no polish style packs found: " + ", ".join(str(candidate) for candidate in candidates),
        what_to_report="The 어체 style packs are missing; nothing was polished.",
        fix="bash modules/agents/skills/install.sh",
        target_files=[str(_SKILL_RELATIVE)],
        details=[
            "The packs ship with the polish-doc skill; syncing the skills module restores them.",
            f"Point {STYLES_ENV} at the directory to override the search.",
        ],
    )


def languages(*, directory: Path | None = None) -> list[str]:
    """Languages the installed packs cover, by directory name."""
    root = directory or styles_dir()
    return sorted(child.name for child in root.iterdir() if child.is_dir() and (child / "L1.md").is_file())


def load_pack(level: int, language: str = DEFAULT_LANGUAGE, *, directory: Path | None = None) -> StylePack:
    if level not in LEVELS:
        raise StylePackError(
            f"unknown 어체 level: {level}",
            what_to_report=f"Level {level} is not one of {', '.join(str(item) for item in LEVELS)}.",
            details=["Levels run 1 (개조식) to 5 (해요체); 3 is the default."],
        )
    root = directory or styles_dir()
    path = root / language / f"L{level}.md"
    if not path.is_file():
        available = ", ".join(languages(directory=root)) or "none"
        raise StylePackError(
            f"style pack missing: {path}",
            what_to_report=f"No L{level} style pack for language {language!r}; nothing was polished.",
            fix="bash modules/agents/skills/install.sh",
            target_files=[str(path)],
            details=[f"Languages with packs installed: {available}."],
        )
    pack = _parse(level, path)
    if pack.language != language:
        raise StylePackError(
            f"style pack {path} declares language {pack.language!r} but is filed under {language!r}",
            what_to_report=f"The L{level} style pack is misfiled; nothing was polished.",
            target_files=[str(path)],
        )
    return pack


def load_all(language: str = DEFAULT_LANGUAGE, *, directory: Path | None = None) -> list[StylePack]:
    root = directory or styles_dir()
    return [load_pack(level, language, directory=root) for level in LEVELS]


def has_prose(text: str, language: str) -> bool:
    """Whether a document carries prose the packs for `language` could polish.

    Unknown languages answer True: this gates whether a file is handed to the
    receiver at all, and a false negative silently drops work the user asked
    for, while a false positive costs one CLEAN mark.
    """
    script = _SCRIPTS.get(language)
    if script is None:
        return True
    stripped = _URL.sub(" ", _INLINE_CODE.sub(" ", _CODE_FENCE.sub(" ", text)))
    match = _FRONTMATTER.match(stripped)
    if match is not None:
        stripped = match.group(2)
    return script.search(stripped) is not None


def _repo_styles_dir() -> Path:
    # Editable installs put this file inside the repository, so the packs are
    # a fixed climb away: <root>/tools/agentkit/src/agentkit/handoff/style.py.
    return Path(__file__).resolve().parents[5] / _SKILL_RELATIVE


def _parse(level: int, path: Path) -> StylePack:
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER.match(text)
    if match is None:
        raise StylePackError(
            f"style pack has no frontmatter: {path}",
            what_to_report=f"The L{level} style pack is malformed; nothing was polished.",
            target_files=[str(path)],
        )
    fields = _fields(match.group(1))
    missing = [key for key in ("name", "language", "label", "ending", "verbosity", "summary") if not fields.get(key)]
    if missing:
        raise StylePackError(
            f"style pack {path} is missing frontmatter keys: {', '.join(missing)}",
            what_to_report=f"The L{level} style pack is malformed; nothing was polished.",
            target_files=[str(path)],
        )
    return StylePack(
        level=level,
        language=fields["language"],
        name=fields["name"],
        label=fields["label"],
        ending=fields["ending"],
        verbosity=fields["verbosity"],
        summary=fields["summary"],
        body=match.group(2).strip(),
        path=path,
    )


def _fields(frontmatter: str) -> dict[str, str]:
    """Flat `key: value` pairs only — the packs have no nesting to parse."""
    fields: dict[str, str] = {}
    for line in frontmatter.splitlines():
        key, separator, value = line.partition(":")
        if not separator or key.strip() != key or not key.strip():
            continue
        fields[key.strip()] = value.strip().strip("\"'")
    return fields
