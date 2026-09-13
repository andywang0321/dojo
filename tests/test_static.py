"""Static analysis at submit: radon cyclomatic complexity + ruff (v0.4)."""

import textwrap

from dojo.static import analyze

CLEAN = textwrap.dedent(
    """
    def is_valid(s: str) -> bool:
        pairs = {")": "(", "]": "[", "}": "{"}
        stack = []
        for ch in s:
            if ch in "([{":
                stack.append(ch)
            elif not stack or stack.pop() != pairs[ch]:
                return False
        return not stack
    """
)

COMPLEX = "def f(n: int) -> int:\n" + "".join(
    f"    if n == {i}:\n        return {i}\n" for i in range(14)
)

RUFFY = "import sys\n\n\ndef f():\n    x=1\n    return x\n"

BROKEN = "def broken(:\n    pass\n"


def test_analyze_clean_code(tmp_path):
    path = tmp_path / "clean.py"
    path.write_text(CLEAN)
    report = analyze(path)
    assert report.complexity, "should list at least the is_valid function"
    entry = next(c for c in report.complexity if c["name"] == "is_valid")
    assert entry["complexity"] <= 10
    assert not report.ruff, "clean code has no lint findings"
    assert report.flags == []


def test_analyze_flags_high_complexity(tmp_path):
    path = tmp_path / "complex.py"
    path.write_text(COMPLEX)
    report = analyze(path)
    entry = next(c for c in report.complexity if c["name"] == "f")
    assert entry["complexity"] > 10
    assert any("f" in flag for flag in report.flags)


def test_analyze_reports_ruff_findings(tmp_path):
    path = tmp_path / "ruffy.py"
    path.write_text(RUFFY)
    report = analyze(path)
    assert report.ruff, "unused import must be flagged"
    codes = {f["code"] for f in report.ruff}
    assert "F401" in codes  # unused import
    assert report.flags


def test_analyze_syntax_error_does_not_crash(tmp_path):
    path = tmp_path / "broken.py"
    path.write_text(BROKEN)
    report = analyze(path)  # must not raise
    assert isinstance(report.complexity, list)


def test_reviewer_prompt_includes_static_findings(tmp_path):
    from dojo.static import analyze
    from dojo.tutor.prompts import build_review_prompt

    path = tmp_path / "complex.py"
    path.write_text(COMPLEX)
    report = analyze(path)
    prompt = build_review_prompt(
        "Return the answer.",
        "def f(n): ...",
        "O(n)",
        "O(1)",
        "O(n)",
        "O(1)",
        "O(n)",
        "O(1)",
        static_analysis=report,
    )
    assert "STATIC ANALYSIS" in prompt
    assert "f" in prompt.split("STATIC ANALYSIS")[1]


def test_analyze_ignores_shebang_executable_rules(tmp_path):
    """The template shebang is dojo's chrome: EXE001/EXE002/EXE004 must not
    be reported as user-code findings (v0.10.10)."""
    from dojo.static import analyze

    path = tmp_path / "shebanged.py"
    path.write_text("#!/Users/x/.venv/bin/python\n\n\ndef two_sum(nums: list[int]) -> list[int]:\n    return [0, 1]\n")
    report = analyze(path)
    codes = {f["code"] for f in report.ruff}
    assert not codes & {"EXE001", "EXE002", "EXE004"}, codes
    assert not report.ruff  # otherwise-clean code stays clean
