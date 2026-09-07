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
