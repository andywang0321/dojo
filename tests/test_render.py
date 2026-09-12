"""AI prose rendering (v0.10.3): markdown in, structure out — ANSI on
TTY-ish consoles, deterministic plain text for pipes/tests."""

from rich.console import Console

from dojo.render import md_plain, render_ai

SAMPLE = """## Two ideas

A **key term** to remember.

- first idea
- second idea

```python
seen = set()
```
"""


def test_md_plain_renders_structure_as_text():
    out = md_plain(SAMPLE)
    assert "Two ideas" in out  # heading text survives
    assert "#" not in out  # heading markers consumed
    assert "**" not in out  # emphasis markers consumed
    assert "key term" in out
    assert "- " not in out.splitlines()[0]  # bullet markers consumed, not leaked
    assert "seen = set()" in out  # fenced code content survives
    assert "```" not in out  # fences consumed


def test_render_ai_emits_ansi_on_color_console():
    console = Console(force_terminal=True, color_system="standard", width=120, no_color=False)
    with console.capture() as cap:
        render_ai(console, "tutor — stack", SAMPLE)
    out = cap.get()
    assert "tutor — stack" in out
    assert "\x1b[" in out  # headings/emphasis styled
    assert "Two ideas" in out


def test_render_ai_plain_path_keeps_content():
    import io

    class Fake:
        def __init__(self):
            self.file = io.StringIO()

        def print(self, *args, **kwargs):
            console = Console(file=self.file, force_terminal=False, no_color=True, width=100)
            console.print(*args, **kwargs)

    fake = Fake()
    render_ai(fake, "teacher — heap", SAMPLE)
    assert "teacher — heap" in fake.file.getvalue()
    assert "Two ideas" in fake.file.getvalue()
