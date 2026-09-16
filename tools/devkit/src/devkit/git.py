"""Read repository-wide diffs without changing the index or worktree."""

import subprocess
from pathlib import Path


def run(args: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, errors="replace")
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Git command failed.")
    return result.stdout


def get_diff(target: str = "staged", exclude: tuple[str, ...] = ()) -> str:
    root = Path(run(["rev-parse", "--show-toplevel"]).strip())
    flags = ["--no-ext-diff", "--no-textconv", "--no-color"]
    if target == "last":
        args = ["show", "--format=", "--root", "--first-parent", "--patch", *flags, "HEAD"]
    else:
        args = ["diff", *flags, "--cached" if target == "staged" else "HEAD"]
    patch = run([*args, "--", ".", *(f":(exclude){path}" for path in exclude)], cwd=root)
    if not patch.strip():
        raise RuntimeError(f"No {target} changes found. Untracked files are not included; stage them explicitly.")
    return patch
