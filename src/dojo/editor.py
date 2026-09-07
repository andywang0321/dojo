"""Editor launching.

The solve loop owns the terminal, so the editor must run elsewhere:

- GUI editors (zed, code, cursor, ...) get a detached process — they open
  their own window and the dojo prompt stays live.
- Terminal editors (nvim, vim, ...) need a fresh terminal: a new tmux
  window when inside tmux, otherwise a new Terminal/iTerm window on macOS.
- Anything unrecognized falls back to the old blocking behavior, with a
  message explaining why.

Override with DOJO_EDITOR (takes precedence over $EDITOR / $VISUAL).
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

GUI_EDITORS = {
    "zed",
    "code",
    "codium",
    "cursor",
    "windsurf",
    "subl",
    "sublime_text",
    "atom",
    "idea",
    "pycharm",
    "clion",
    "goland",
    "rider",
    "webstorm",
    "textmate",
    "mate",
    "nova",
    "fleet",
}

TERMINAL_EDITORS = {
    "nvim",
    "vim",
    "vi",
    "nano",
    "micro",
    "helix",
    "emacs",
    "emacsclient",
    "kak",
    "vis",
    "ed",
    "pico",
}


def editor_command() -> str:
    return (
        os.environ.get("DOJO_EDITOR")
        or os.environ.get("EDITOR")
        or os.environ.get("VISUAL")
        or "vi"
    )


def _first_word(cmd: str) -> str:
    parts = shlex.split(cmd)
    return Path(parts[0]).name.lower() if parts else ""


def is_gui_editor(cmd: str) -> bool:
    return _first_word(cmd) in GUI_EDITORS


def is_terminal_editor(cmd: str) -> bool:
    return _first_word(cmd) in TERMINAL_EDITORS


def _apple_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _osascript_command(cmd: str, path: str) -> list[str] | None:
    """Build an osascript invocation that opens cmd+path in a new macOS
    terminal window. Terminal.app is the default; iTerm2 when that's the
    active terminal program."""
    if sys.platform != "darwin" or not shutil.which("osascript"):
        return None
    term_program = os.environ.get("TERM_PROGRAM", "")
    shell_cmd = f"{cmd} {shlex.quote(path)}"
    if "iTerm" in term_program:
        script = (
            'tell application "iTerm" to create window with default profile '
            f'command "{_apple_escape(shell_cmd)}"'
        )
    else:
        script = f'tell application "Terminal" to do script "{_apple_escape(shell_cmd)}"'
    return ["osascript", "-e", script]


def _tmux_command(cmd: str, path: str) -> list[str] | None:
    if not (os.environ.get("TMUX") and shutil.which("tmux")):
        return None
    return ["tmux", "new-window", f"{cmd} {shlex.quote(path)}"]


def launch(path: Path) -> str:
    """Open ``path`` in the configured editor without blocking the dojo
    prompt, when the environment allows it. Returns a human message."""
    cmd = editor_command()
    args = shlex.split(cmd) + [str(path)]

    if is_gui_editor(cmd):
        subprocess.Popen(
            args,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return f"Opened {path.name} with {_first_word(cmd)} — the dojo prompt stays live."

    if is_terminal_editor(cmd):
        tmux_cmd = _tmux_command(cmd, str(path))
        if tmux_cmd:
            subprocess.Popen(
                tmux_cmd, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            return f"Opened {path.name} in a new tmux window — the dojo prompt stays live."

        apple_cmd = _osascript_command(cmd, str(path))
        if apple_cmd:
            proc = subprocess.run(apple_cmd, capture_output=True, text=True)
            if proc.returncode == 0:
                return f"Opened {path.name} in a new terminal window — the dojo prompt stays live."

        # Terminal editor, no way to detach: fall back to blocking.
        subprocess.call(args)
        return (
            "Editor closed; back to the dojo prompt. (Terminal editors block the "
            "prompt unless you run inside tmux or on macOS — set DOJO_EDITOR to a "
            "GUI editor for background editing.)"
        )

    # Unrecognized editor: assume terminal-like and block, as before.
    subprocess.call(args)
    return (
        "Editor closed; back to the dojo prompt. (Unknown editor treated as "
        "blocking — add it to GUI_EDITORS in src/dojo/editor.py if it can detach.)"
    )
