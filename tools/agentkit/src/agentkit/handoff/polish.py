"""Polish changed Markdown documents via a headless `agy` run.

Unlike the commit tasks, the outcome here is edited files, not commits. The
same trust rule applies — never believe agy's exit status — so the runner
hashes every target before and after and reports from that. A target agy left
untouched is only a legitimate no-op when its reply marks the file CLEAN;
unchanged and unmarked reads as "nothing happened", not "nothing was needed".

Rollback is arranged before agy runs, never after: targets git can restore are
staged first, so `git restore <file>` afterwards undoes exactly the polish,
and files git cannot restore (outside the repository, or ignored) are copied
into the scratch space.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from .. import gitutil
from ..agy import AgyClient, AgyRun, missing_rules
from ..agy.diagnose import FailureTexts, diagnose_failure
from ..errors import (
    Actor,
    Advisory,
    AgyNotInstalledError,
    AgyPermissionError,
    ConfigError,
    ErrorCode,
    ExitCode,
    GitCommandError,
    NotAGitRepoError,
    Retry,
)
from ..repoconfig import load_polish_config
from ..scratch import is_ignored, resolve_scratch
from ..ui import Reporter
from .style import DEFAULT_LANGUAGE, DEFAULT_LEVEL, LEVELS, StylePack, has_prose, load_pack

MD_SUFFIXES = {".md", ".markdown"}
SCOPE_CHANGED = "changed-regions"
SCOPE_WHOLE = "whole-file"
ROLLBACK_INDEX = "index"  # pre-polish state staged; `git restore <file>` undoes
ROLLBACK_BACKUP = "backup"  # pre-polish copy in scratch; copy back to undo

# The one git command the receiver needs: reading the change it is scoped to.
# The permitted set matches the grants exactly — a wider prompt would classify
# a denial of e.g. `git status` as in-scope and prescribe a grant fix that
# grants nothing new, sending the caller into a retry loop against the wall.
POLISH_GRANTS: tuple[str, ...] = ("command(git diff)",)
PERMITTED_POLISH_COMMANDS: tuple[str, ...] = ("git diff",)

_POLISH_RULES = """Rules:
- Edit the target files in place with your file-editing tools — edits are
  pre-approved in this session. Never print a rewrite instead of applying it.
- The only shell command permitted is read-only `git diff`, used as shown
  below. Everything else — git status, git log, git add, git commit,
  git restore, cat, ls — is denied. A denial is not a reason to stop: carry
  on with the remaining files and finish the job.
- For a changed-regions target, polish only the text its pending change
  touches: {diff_command} shows the change. Rewrite touched sentences and
  paragraphs as a whole, but leave everything the diff does not touch
  byte-identical.
- For a whole-file target, polish the entire document.
- The target language is {language}. Prose in any other language stays
  byte-identical, and a target with no {language} prose at all is CLEAN.
- Never alter code blocks, inline code, frontmatter, URLs, link targets, file
  paths, identifiers, or command names. Prose only."""

# Style packs are inlined rather than left for the receiver to read: the skill
# directory sits outside agy's --add-dir scope, and a soft-denied read would
# polish at the default register and report success all the same.
_POLISH_STYLE_HEADER = """Style packs — apply to each target exactly the pack its group above names. A
pack outranks the skill's own default style rules wherever the two disagree;
apply it to prose only, within the scope that target already has."""

_POLISH_STYLE_SECTION = """===== 어체 {title} · {language} =====
{summary}

{body}"""

_POLISH_CONTRACT = """When you are done, end your reply with exactly one line per target file:
POLISHED: <file>   — you changed the file
CLEAN: <file>      — the file needed no changes

Then one more line per target file, naming the 어체 you applied to it:
STYLE: <file> {style_name}

Write each path exactly as it appears in the target list above."""


class PolishPreflightError(ConfigError):
    """A refused polish command line.

    Exit 1, not ConfigError's default 2: this command's exit-code contract
    reserves 2 for runs that polished some files and left others unaccounted,
    and a refusal that touched nothing must not read as half-done work.
    """

    exit_code = ExitCode.FAILED


@dataclass(frozen=True)
class PolishTarget:
    path: Path  # absolute
    display: str  # repo-relative where possible; what the prompt shows
    scope: str  # SCOPE_CHANGED or SCOPE_WHOLE
    rollback: str  # ROLLBACK_INDEX or ROLLBACK_BACKUP


@dataclass
class PolishResult:
    exit_code: ExitCode
    polished: list[str] = field(default_factory=list)
    clean: list[str] = field(default_factory=list)
    unaccounted: list[str] = field(default_factory=list)
    backup_dir: Path | None = None


def polish_prompt(
    workdir: Path,
    assignments: list[tuple[PolishTarget, StylePack]],
    base: str | None,
    instructions: tuple[str, ...],
) -> str:
    diff_command = "`git diff --cached -- <file>`" if base is None else f"`git diff --cached {base} -- <file>`"
    groups = _group_by_pack(assignments)
    lines = [
        "/polish-doc",
        "",
        f"Work in {workdir} — polish the Markdown files listed below.",
        "",
        _POLISH_RULES.format(diff_command=diff_command, language=groups[0][0].language_name),
        "",
        "Targets (scope :: file), grouped by the 어체 each one is polished into:",
    ]
    for pack, targets in groups:
        lines += ["", f"[{pack.title}]", *(f"- {target.scope} :: {target.display}" for target in targets)]
    lines += ["", _POLISH_STYLE_HEADER]
    for pack, _ in groups:
        lines += [
            "",
            _POLISH_STYLE_SECTION.format(
                title=pack.title, language=pack.language_name, summary=pack.summary, body=pack.body
            ),
        ]
    if instructions:
        lines += [
            "",
            "Caller instructions — these outrank the style pack and the default style rules where they conflict:",
            *(f"  {i}. {instruction}" for i, instruction in enumerate(instructions, start=1)),
        ]
    lines += ["", _POLISH_CONTRACT.format(style_name=groups[0][0].name)]
    return "\n".join(lines) + "\n"


def _group_by_pack(assignments: list[tuple[PolishTarget, StylePack]]) -> list[tuple[StylePack, list[PolishTarget]]]:
    groups: dict[str, tuple[StylePack, list[PolishTarget]]] = {}
    for target, pack in assignments:
        groups.setdefault(pack.name, (pack, []))[1].append(target)
    return [groups[name] for name in sorted(groups, key=lambda name: groups[name][0].level)]


def run_polish(
    paths: tuple[Path, ...] = (),
    *,
    base: str | None = None,
    level: int | None = None,
    language: str = DEFAULT_LANGUAGE,
    instructions: tuple[str, ...] = (),
    client: AgyClient,
    reporter: Reporter | None = None,
    cwd: Path | None = None,
    verbose: bool = False,
) -> PolishResult:
    out = reporter or Reporter("handoff-polish")

    if not client.available:
        raise AgyNotInstalledError(
            f"{client.executable} not found on PATH.",
            what_to_report="Antigravity CLI (agy) is not installed; cannot run the polish handoff.",
            details=[f"Install the Antigravity CLI and make sure `{client.executable}` is on PATH."],
        )
    if base is not None and paths:
        raise PolishPreflightError(
            "--base only applies when no explicit paths are given.",
            what_to_report="--base and explicit paths were combined; pass one or the other.",
            details=["Explicit paths are always polished whole, so a diff base has nothing to scope."],
        )

    # Before anything is staged: a run that cannot name its 어체 must not
    # start, or it silently polishes at whatever register the receiver assumes.
    # The explicit flag is resolved here; a per-path map needs the targets.
    default_pack = load_pack(DEFAULT_LEVEL if level is None else level, language)

    root: Path | None
    try:
        root = gitutil.repo_root(cwd=cwd)
    except NotAGitRepoError:
        if not paths:
            raise
        root = None  # pure path mode: no git, backup-only rollback
    workdir = root or cwd or Path.cwd()

    if paths:
        targets = _explicit_targets(paths, root)
    else:
        assert root is not None
        targets = _changed_md_targets(root, base)
    if not targets:
        out.note("No changed Markdown files to polish. Skipping handoff.")
        return PolishResult(ExitCode.OK)

    targets = _apply_language_filter(targets, default_pack, out)
    if not targets:
        out.note(f"No changed Markdown with {default_pack.language_name} prose. Skipping handoff.")
        return PolishResult(ExitCode.OK)

    assignments = _assign_packs(targets, default_pack, language, level_given=level is not None, root=root, out=out)
    packs = {pack.name for _, pack in assignments}
    if level is not None and any(target.scope == SCOPE_CHANGED for target in targets):
        out.note(
            f"{default_pack.title} applies to the changed regions only — prose the diff does not touch keeps "
            "its current 어체. Pass the file as an explicit path to re-register the whole document."
        )

    if any(target.scope == SCOPE_CHANGED for target in targets):
        missing = missing_rules(POLISH_GRANTS)
        if missing:
            raise AgyPermissionError(
                "agy is missing required permission grants: " + ", ".join(missing),
                fix="agentkit agy grant",
                what_to_report="agy execution permissions are missing; authorization is required.",
                details=[
                    "Headless agy cannot prompt, so it could not read the diff it must scope to.",
                    f"Missing grants: {', '.join(missing)}",
                ],
            )

    result = PolishResult(ExitCode.OK)
    _stage_for_rollback(root, targets, out)
    result.backup_dir = _backup_for_rollback(root or cwd, targets, out)
    before = {target.path: _digest(target.path) for target in targets}

    registers = default_pack.title if len(packs) == 1 else f"{len(packs)} 어체"
    out.note(
        f"Delegating {len(targets)} Markdown file(s) to agy in {registers} "
        f"(effort={client.effort}, timeout={client.timeout}, mode={client.mode})…"
    )
    prompt = polish_prompt(workdir, assignments, base, instructions)
    extra_dirs = sorted({target.path.parent for target in targets if not _within(target.path, workdir)})
    run = client.run(prompt, add_dir=workdir, extra_dirs=extra_dirs)
    if verbose:
        out.block("agy output", run.output)

    marks = _parse_marks(run.output, targets)

    # A vanished target is receiver misbehavior, not an agentkit crash: name
    # it, point at its rollback, and let it fail the run as unaccounted.
    missing = [target for target in targets if not target.path.is_file()]
    for target in missing:
        undo = (
            f"`git restore {target.display}` brings it back"
            if target.rollback == ROLLBACK_INDEX
            else f"a pre-run copy is in {result.backup_dir}"
        )
        out.warn(f"{target.display} no longer exists — agy deleted or renamed it; {undo}.")

    present = [target for target in targets if target not in missing]
    changed = [target for target in present if _digest(target.path) != before[target.path]]
    untouched = [target for target in present if target not in changed]
    result.polished = [target.display for target in changed]
    result.clean = [target.display for target in untouched if marks.get(target.display) == "CLEAN"]
    result.unaccounted = [target.display for target in missing] + [
        target.display for target in untouched if marks.get(target.display) != "CLEAN"
    ]

    if not changed:
        if not result.unaccounted:
            out.note(f"All {len(targets)} file(s) reviewed and reported CLEAN — nothing needed changing.")
            return result
        result.exit_code = _report_no_edits(out, run, result, verbose=verbose)
        return result

    for target in changed:
        if marks.get(target.display) == "CLEAN":
            out.warn(f"{target.display} was marked CLEAN but its content changed — review it with extra care.")
    for target in untouched:
        if marks.get(target.display) == "POLISHED":
            out.warn(f"{target.display} was marked POLISHED but is byte-identical — treating it as not polished.")

    _check_style_marks(run.output, [(target, pack) for target, pack in assignments if target in changed], out)
    out.note(f"Polished {len(changed)} file(s) in {registers}:")
    _detail_changes(out, root, changed)
    if result.clean:
        out.note(f"{len(result.clean)} file(s) needed no changes: {', '.join(result.clean)}")
    _note_rollback(out, targets, result.backup_dir)

    if result.unaccounted:
        if not verbose:
            out.block("agy output", run.output)
        out.advise(
            Advisory(
                code=ErrorCode.POLISH_INCOMPLETE,
                actor=Actor.NONE,
                retry=Retry.UNSAFE,
                what_to_report=(
                    f"{len(changed)} file(s) were polished, but the files below came back "
                    "untouched and unmarked. Re-running would re-polish the finished ones; "
                    "hand the leftovers back explicitly if they still need work."
                ),
            ),
            "some files were left untouched without a CLEAN mark.",
        )
        out.detail(result.unaccounted)
        result.exit_code = ExitCode.INCOMPLETE
    return result


def _assign_packs(
    targets: list[PolishTarget],
    default_pack: StylePack,
    language: str,
    *,
    level_given: bool,
    root: Path | None,
    out: Reporter,
) -> list[tuple[PolishTarget, StylePack]]:
    """One pack per target: an explicit --level wins, otherwise the repo map.

    The map lets one run polish an ADR into 해라체 and a README into 합니다체,
    which two runs cannot do: the second sweep would find the first run's files
    still changed against HEAD and re-register them at its own level.
    """
    if level_given or root is None:
        return [(target, default_pack) for target in targets]

    config = load_polish_config(cwd=root, valid_levels=LEVELS)
    if not config.levels:
        return [(target, default_pack) for target in targets]

    packs = {default_pack.level: default_pack}
    assignments = []
    for target in targets:
        level = config.level_for(target.display)
        if level is not None and level not in packs:
            packs[level] = load_pack(level, language)
        assignments.append((target, packs[default_pack.level if level is None else level]))

    if len(packs) > 1:
        out.note(f"어체 from {config.path}:")
        out.detail(
            [f"{pack.title}: {', '.join(t.display for t in group)}" for pack, group in _group_by_pack(assignments)]
        )
    return assignments


def _apply_language_filter(targets: list[PolishTarget], pack: StylePack, out: Reporter) -> list[PolishTarget]:
    """Drop discovered targets the packs cannot help, keep the named ones.

    A changed-file sweep picks up whatever is in the tree, and handing an
    English-only document to a Korean polisher spends quota to be told CLEAN.
    An explicit path is a different thing entirely — the user named that file —
    so it is flagged and sent anyway.
    """
    kept, skipped = [], []
    for target in targets:
        if has_prose(target.path.read_text(encoding="utf-8", errors="replace"), pack.language):
            kept.append(target)
        elif target.scope == SCOPE_WHOLE:  # named on the command line
            out.warn(f"{target.display} has no {pack.language_name} prose, but you named it — sending it anyway.")
            kept.append(target)
        else:
            skipped.append(target)
    if skipped:
        out.note(f"Skipped {len(skipped)} file(s) with no {pack.language_name} prose:")
        out.detail([target.display for target in skipped])
    return kept


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _split_z(output: str) -> set[str]:
    return {name for name in output.split("\0") if name}


def _changed_md_targets(root: Path, base: str | None) -> list[PolishTarget]:
    """Markdown files changed against `base` (default HEAD), plus untracked ones."""
    ref = base or "HEAD"
    if base is not None:
        try:
            gitutil.run(["rev-parse", "--verify", "--quiet", f"{base}^{{commit}}"], cwd=root)
        except GitCommandError as error:
            raise PolishPreflightError(
                f"--base {base!r} is not a commit this repository knows.",
                what_to_report=f"The --base ref {base!r} does not resolve; nothing was polished.",
                details=["Pass a branch, tag, or commit reachable from this repository."],
            ) from error

    # -z output is NUL-separated and unquoted. Line output would octal-escape
    # and quote non-ASCII names (core.quotepath default), silently dropping
    # Korean-named files — exactly the ones this feature exists for.
    names: set[str] = set()
    if gitutil.head_sha(cwd=root):  # an unborn branch has no diff base
        names |= _split_z(gitutil.run(["diff", "--name-only", "-z", ref], cwd=root))
    names |= _split_z(gitutil.run(["ls-files", "--others", "--exclude-standard", "-z"], cwd=root))

    targets = []
    for name in sorted(names):
        path = root / name
        if Path(name).suffix.lower() not in MD_SUFFIXES or not path.is_file():
            continue
        targets.append(PolishTarget(path=path, display=name, scope=SCOPE_CHANGED, rollback=ROLLBACK_INDEX))
    return targets


def _explicit_targets(paths: tuple[Path, ...], root: Path | None) -> list[PolishTarget]:
    targets = []
    for given in paths:
        path = given.expanduser().resolve()
        if path.suffix.lower() not in MD_SUFFIXES:
            raise PolishPreflightError(
                f"not a Markdown file: {given}",
                what_to_report=f"{given} is not a Markdown file; the polish handoff only takes .md/.markdown.",
            )
        if not path.is_file():
            raise PolishPreflightError(
                f"file not found: {given}",
                what_to_report=f"{given} does not exist; nothing was polished.",
            )
        display, rollback = str(path), ROLLBACK_BACKUP
        if root is not None and _within(path, root):
            rel = str(path.relative_to(root))
            display = rel
            # git restore cannot bring back an ignored file's old content, so
            # ignored targets fall back to the scratch backup like external ones.
            if not is_ignored(rel, root):
                rollback = ROLLBACK_INDEX
        targets.append(PolishTarget(path=path, display=display, scope=SCOPE_WHOLE, rollback=rollback))
    return targets


def _stage_for_rollback(root: Path | None, targets: list[PolishTarget], out: Reporter) -> None:
    """Put the pre-polish state into the index, so `git restore` undoes agy only."""
    stageable = [target for target in targets if target.rollback == ROLLBACK_INDEX]
    if root is None or not stageable:
        return
    displays = [target.display for target in stageable]
    # -z keeps non-ASCII paths unquoted, same as the target resolution above.
    for entry in gitutil.run(["status", "--porcelain", "-z", "--", *displays], cwd=root).split("\0"):
        if len(entry) >= 4 and entry[0] not in " ?" and entry[1] not in " ?":
            out.warn(f"{entry[3:]} had both staged and unstaged changes; staging collapses that split.")
    gitutil.run(["add", "--", *displays], cwd=root)
    out.note(f"Staged {len(stageable)} file(s) — after the polish, `git restore <file>` undoes it.")


def _backup_for_rollback(root: Path | None, targets: list[PolishTarget], out: Reporter) -> Path | None:
    unstageable = [target for target in targets if target.rollback == ROLLBACK_BACKUP]
    if not unstageable:
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup_dir = resolve_scratch(cwd=root, subdir=f"polish-backup/{stamp}").path
    for index, target in enumerate(unstageable):
        shutil.copy2(target.path, backup_dir / f"{index:02d}-{target.path.name}")
    out.note(f"Backed up {len(unstageable)} file(s) git cannot restore to {backup_dir} — copy back to undo.")
    return backup_dir


_STYLE_MARK = re.compile(r"\s*[-*>`\s]*STYLE:")
_LEVEL_TOKEN = re.compile(r"\b(L[1-5])\b")


def _path_patterns(targets: list[PolishTarget]) -> dict[str, re.Pattern[str]]:
    """Locate a target's path inside a line, by either spelling.

    Attribution is by the exact display or absolute path with boundary guards
    — never by basename, which could attach a mark meant for some other file
    the receiver happened to mention.
    """
    return {
        target.display: re.compile(
            r"(?<![\w./\\-])(?:" + re.escape(str(target.path)) + "|" + re.escape(target.display) + r")(?![\w-])"
        )
        for target in targets
    }


def _parse_style_marks(output: str, targets: list[PolishTarget]) -> dict[str, str]:
    """Match `STYLE: <file> L2` lines back to targets."""
    patterns = _path_patterns(targets)
    marks: dict[str, str] = {}
    for line in output.splitlines():
        if _STYLE_MARK.match(line) is None:
            continue
        level = _LEVEL_TOKEN.search(line)
        if level is None:
            continue
        for display, pattern in patterns.items():
            if pattern.search(line):
                marks[display] = level.group(1)
    return marks


def _parse_marks(output: str, targets: list[PolishTarget]) -> dict[str, str]:
    """Match POLISHED/CLEAN lines back to targets.

    Receivers decorate contract lines despite the instructions (backticks,
    dashes, trailing notes), so the path is located inside the mark line
    rather than parsed out of it. A CLEAN mark has no hash backstop, so
    path-exact attribution is the only thing tying it to the actual target.
    """
    patterns = _path_patterns(targets)
    marks: dict[str, str] = {}
    for line in output.splitlines():
        head = re.match(r"\s*[-*>`\s]*(POLISHED|CLEAN)\b", line)
        if head is None:
            continue
        for display, pattern in patterns.items():
            if pattern.search(line):
                marks[display] = head.group(1)
    return marks


def _check_style_marks(output: str, assignments: list[tuple[PolishTarget, StylePack]], out: Reporter) -> None:
    """Confirm each polished file came back under the pack it was given.

    The edits themselves are already covered by the hashes, so a bad mark
    warns instead of failing the run. What it catches is the failure the
    hashes cannot see: a file polished at the wrong register, which looks like
    a clean success and shows up only in the diff. With a level map in play
    that is a per-file question, so the mark is per file too.
    """
    if not assignments:
        return
    marks = _parse_style_marks(output, [target for target, _ in assignments])
    wrong = [
        f"{target.display}: asked {pack.name}, applied {marks[target.display]}"
        for target, pack in assignments
        if target.display in marks and marks[target.display] != pack.name
    ]
    unmarked = [target.display for target, _ in assignments if target.display not in marks]
    if wrong:
        out.warn("The polisher applied a different 어체 than it was given — `git restore <file>` undoes it.")
        out.detail(wrong)
    if unmarked:
        out.warn(
            f"{len(unmarked)} polished file(s) came back without a STYLE line — "
            "check the 어체 in `git diff` before keeping them."
        )
        out.detail(unmarked)


def _detail_changes(out: Reporter, root: Path | None, changed: list[PolishTarget]) -> None:
    in_repo = [target.display for target in changed if target.rollback == ROLLBACK_INDEX]
    if root is not None and in_repo:
        stat = gitutil.run(["diff", "--stat", "--", *in_repo], cwd=root).rstrip()
        if stat:
            out.detail(stat.splitlines())
    for target in changed:
        if target.rollback == ROLLBACK_BACKUP:
            out.detail([str(target.path)])


def _note_rollback(out: Reporter, targets: list[PolishTarget], backup_dir: Path | None) -> None:
    if any(target.rollback == ROLLBACK_INDEX for target in targets):
        out.note("Review with `git diff`; undo a file with `git restore <file>`; the staged version is pre-polish.")
    if backup_dir is not None:
        out.note(f"Pre-polish copies of the other file(s) are in {backup_dir}.")


def _report_no_edits(out: Reporter, run: AgyRun, result: PolishResult, *, verbose: bool) -> ExitCode:
    """Nothing changed and not every file was marked CLEAN: name the cause.

    Nothing was touched, so unlike a partial commit there is no half-done work
    to protect — waiting causes (quota, timeout) may safely be retried later.
    """
    if not verbose:
        out.block("agy output", run.output)
    out.error("agy left no polished result — no target file changed.")

    left = "No files were modified."
    texts = FailureTexts(
        nothing_happened="no files were polished",
        timeout_cause="agy timed out before it edited anything.",
        timeout_report="agy timed out before polishing anything. A larger --timeout, or fewer files, usually fixes it.",
        timeout_hint="A larger --timeout, or fewer files, is the usual answer.",
        unknown_cause="agy gave no recognizable reason.",
        unknown=Advisory(
            code=ErrorCode.NO_FILES_POLISHED,
            actor=Actor.NONE,
            retry=Retry.UNSAFE,
            what_to_report="agy neither edited nor cleared the files. See the agy output above for the cause.",
            details=(f"Unaccounted files: {', '.join(result.unaccounted)}", left, "No retry was attempted."),
        ),
    )
    cause, advisory = diagnose_failure(
        run,
        permitted=PERMITTED_POLISH_COMMANDS,
        texts=texts,
        left=left,
        after_fix=Retry.AFTER_FIX,
        wait_it_out=Retry.SAFE,
    )
    out.advise(advisory, cause)
    return ExitCode.FAILED
