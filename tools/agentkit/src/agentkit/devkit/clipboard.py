"""Optional desktop clipboard support, independent of agentkit."""

import shutil
import subprocess
import sys
from pathlib import Path


def _run(command: list[str], data: bytes | None = None) -> None:
    try:
        subprocess.run(command, input=data, check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise RuntimeError(f"Clipboard unavailable: {error}") from error


def copy_text(text: str) -> None:
    if sys.platform == "darwin":
        _run(["pbcopy"], text.encode("utf-8"))
    elif sys.platform == "win32":
        _run(["clip"], text.encode("utf-16le"))
    else:
        for command, encoding in [
            (["clip.exe"], "utf-16le"),
            (["wl-copy"], "utf-8"),
            (["xclip", "-selection", "clipboard"], "utf-8"),
            (["xsel", "--clipboard", "--input"], "utf-8"),
        ]:
            if shutil.which(command[0]):
                try:
                    _run(command, text.encode(encoding))
                    return
                except RuntimeError:
                    continue
        raise RuntimeError("Clipboard unavailable. Install wl-copy, xclip or xsel, or use --stdout.")


def copy_file(path: Path) -> None:
    if sys.platform != "darwin":
        raise RuntimeError("File clipboard is supported only on macOS; use the printed file path.")
    script = "on run argv\nset the clipboard to (POSIX file (item 1 of argv) as «class furl»)\nend run"
    _run(["osascript", "-e", script, str(path.resolve())])
