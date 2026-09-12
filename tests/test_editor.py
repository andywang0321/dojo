"""Editor launching classification (spawning itself is environment-dependent,
so only the pure helpers are tested)."""

from dojo.editor import is_gui_editor, is_terminal_editor


def test_gui_editor_classification():
    assert is_gui_editor("zed")
    assert is_gui_editor("code --wait")
    assert is_gui_editor("/Applications/Zed.app/Contents/MacOS/zed")
    assert not is_gui_editor("nvim")


def test_terminal_editor_classification():
    assert is_terminal_editor("nvim")
    assert is_terminal_editor("vim")
    assert is_terminal_editor("vi -u NONE")
    assert not is_terminal_editor("zed")


def test_unknown_editors_are_neither():
    assert not is_gui_editor("mysteryeditor")
    assert not is_terminal_editor("mysteryeditor")


def test_open_path_folder_editors_open_folder_and_file():
    from pathlib import Path

    from dojo.editor import open_path

    for cmd in ("code", "zed", "cursor"):
        targets, message = open_path(cmd, Path("/wb/two_sum.py"))
        assert targets == [Path("/wb"), Path("/wb/two_sum.py")]  # folder + focused file
        assert "workbench folder" in message
    targets, _ = open_path("subl", Path("/wb/two_sum.py"))
    assert targets == [Path("/wb/two_sum.py")]  # other editors keep just the file


def test_ensure_ide_config_generates_self_contained_workspace(tmp_path):
    from dojo.editor import ensure_ide_config

    venv = tmp_path / ".venv" / "bin" / "python"
    ensure_ide_config(tmp_path, venv_python=venv)
    settings = (tmp_path / ".vscode" / "settings.json").read_text()
    launch = (tmp_path / ".vscode" / "launch.json").read_text()
    workspace = (tmp_path / "workbench.code-workspace").read_text()
    assert str(venv) in settings
    assert "debugpy" in launch and "${file}" in launch
    assert "folders" in workspace and str(venv) in workspace
    zed_debug = (tmp_path / ".zed" / "debug.json").read_text()
    assert "Debugpy" in zed_debug and "$ZED_FILE" in zed_debug
    assert str(venv) in zed_debug  # the debugpy "python" key pins the venv
    ensure_ide_config(tmp_path, venv_python=venv)  # idempotent
