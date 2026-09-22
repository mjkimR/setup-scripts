import subprocess

from devkit import clipboard


def test_macos_file_path_is_an_argument(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(clipboard.sys, "platform", "darwin")
    monkeypatch.setattr(clipboard.subprocess, "run", lambda *a, **kw: calls.append((a, kw)))
    path = tmp_path / 'a"quoted\\file.txt'
    clipboard.copy_file(path)
    command = calls[0][0][0]
    assert command[-1] == str(path)
    assert str(path) not in command[2]


def test_wayland_falls_back_when_unavailable(monkeypatch):
    monkeypatch.setattr(clipboard.sys, "platform", "linux")
    monkeypatch.setattr(clipboard.shutil, "which", lambda name: name if name in {"wl-copy", "xclip"} else None)
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if command[0] == "wl-copy":
            raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(clipboard.subprocess, "run", run)
    clipboard.copy_text("hello")
    assert [c[0] for c in calls] == ["wl-copy", "xclip"]
