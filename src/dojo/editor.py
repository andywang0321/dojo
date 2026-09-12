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

#: Editors that are happiest opening the workbench *folder* (their project
#: config lives in .vscode/ or .zed/ rather than a bare file (v0.10.6,
#: zed added v0.10.7).
FOLDER_EDITORS = {"code", "codium", "cursor", "windsurf", "zed"}

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


def open_path(cmd: str, path: Path) -> tuple[list[Path], str]:
    """What to open, and what to tell the user: VSCode-family editors and
    Zed get the workbench *folder plus the file* — the folder carries the
    generated .vscode/ or .zed/ config (debugger wired without knowing
    the repo exists) and the file is the focused pane (v0.10.8: folder
    alone left the editor staring at an empty workspace); everyone else
    gets just the file."""
    if _first_word(cmd) in FOLDER_EDITORS:
        return [path.parent, path], (
            f"Opened the workbench folder with {_first_word(cmd)} — the "
            "generated debugger config points at dojo's Python. The dojo "
            "prompt stays live."
        )
    return [path], (
        f"Opened {path.name} with {_first_word(cmd)} — the dojo prompt stays live."
    )


def ensure_ide_config(workbench_dir: Path, venv_python: Path | None = None) -> None:
    """Generate the self-contained IDE workspaces inside the workbench
    (v0.10.6, zed v0.10.7): opening this folder — or the generated
    workbench.code-workspace — wires the debugger to dojo's venv with
    zero repo knowledge. Idempotent; rewritten each session so path
    moves self-heal. Uses the runtime config when paths are not injected
    (tests inject tmp paths)."""
    import json

    from dojo.config import VENV_PYTHON as runtime_venv

    venv_python = venv_python or runtime_venv
    interpreter = str(venv_python)

    vscode = workbench_dir / ".vscode"
    vscode.mkdir(parents=True, exist_ok=True)
    (vscode / "settings.json").write_text(
        '{\n  // dojo-generated: user code in this folder runs on dojo\'s venv.\n'
        f'  "python.defaultInterpreterPath": "{interpreter}"\n'
        "}\n"
    )
    (vscode / "launch.json").write_text(
        '{\n  "version": "0.2.0",\n  "configurations": [\n    {\n'
        '      "name": "dojo: debug the active workbench file",\n'
        '      "type": "debugpy",\n      "request": "launch",\n'
        '      "program": "${file}",\n'
        '      "console": "integratedTerminal",\n      "justMyCode": true\n'
        "    }\n  ]\n}\n"
    )
    (workbench_dir / "workbench.code-workspace").write_text(
        '{\n  // dojo-generated: open this file in VSCode to debug workbench code.\n'
        '  "folders": [{"path": "."}],\n'
        '  "settings": {"python.defaultInterpreterPath": "%s"}\n}\n' % interpreter
    )

    # Zed (v0.10.7): its integrated debugger uses the debugpy adapter; the
    # explicit "python" key pins dojo's venv so the toolchain detection
    # (which can't see a venv outside the worktree) is never needed.
    zed = workbench_dir / ".zed"
    zed.mkdir(parents=True, exist_ok=True)
    (zed / "debug.json").write_text(
        json.dumps(
            [
                {
                    "label": "dojo: debug the active workbench file",
                    "adapter": "Debugpy",
                    "program": "$ZED_FILE",
                    "request": "launch",
                    "python": interpreter,
                    "justMyCode": True,
                }
            ],
            indent=2,
        )
        + "\n"
    )


def launch(path: Path) -> str:
    """Open ``path`` in the configured editor without blocking the dojo
    prompt, when the environment allows it. Returns a human message."""
    cmd = editor_command()
    targets, message = open_path(cmd, path)
    args = shlex.split(cmd) + [str(target) for target in targets]

    if is_gui_editor(cmd):
        subprocess.Popen(
            args,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return message

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
