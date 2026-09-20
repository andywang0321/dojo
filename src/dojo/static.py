"""Static analysis at submit (v0.4): radon cyclomatic complexity + ruff.

Evidence for the reviewer and the learner, not a verdict: complexity above
the McCabe convention (10) and lint findings are flags, never failures.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
import tempfile
from pathlib import Path

from dojo.config import LOGS_DIR

COMPLEXITY_THRESHOLD = 10  # the McCabe convention


@dataclass
class StaticReport:
    complexity: list[dict] = field(default_factory=list)  # {name, complexity, rank}
    ruff: list[dict] = field(default_factory=list)  # {code, message, line}
    notes: list[str] = field(default_factory=list)  # tooling hiccups, if any

    @property
    def flags(self) -> list[str]:
        out = []
        for entry in self.complexity:
            if entry["complexity"] > COMPLEXITY_THRESHOLD:
                out.append(
                    f"{entry['name']}: complexity {entry['complexity']} "
                    f"(rank {entry['rank']}) — consider refactoring"
                )
        for finding in self.ruff[:5]:
            out.append(
                f"ruff {finding['code']} line {finding['line']}: {finding['message']}"
            )
        return out

    def to_dict(self) -> dict:
        return {
            "complexity": self.complexity,
            "ruff": self.ruff,
            "notes": self.notes,
        }


def analyze(code_path: Path, source: str | None = None) -> StaticReport:
    """Cyclomatic complexity per function (radon) + lint findings (ruff).

    Never raises — including when the file cannot be read at all: the read used
    to sit outside both try blocks, so a missing file (FileNotFoundError) or a
    non-UTF-8 one (UnicodeDecodeError) escaped `_check` and could lose a passing
    submit (v0.13 audit, S2.25)."""
    report = StaticReport()
    lint_source = source
    if lint_source is None:
        try:
            lint_source = code_path.read_text()
        except (OSError, UnicodeDecodeError) as exc:
            report.notes.append(f"static analysis skipped: {type(exc).__name__}: {exc}")
            return report

    try:
        from radon.complexity import cc_visit
        from radon.visitors import Function

        for block in cc_visit(lint_source):
            if isinstance(block, Function):
                report.complexity.append(
                    {
                        "name": block.name,
                        "complexity": block.complexity,
                        # radon ≥ 5: the A-F grade is `.letter`; older: `.rank`
                        "rank": getattr(block, "letter", None)
                        or getattr(block, "rank", ""),
                    }
                )
    except Exception as exc:  # noqa: BLE001 - evidence gathering must survive
        report.notes.append(f"radon skipped: {exc}")

    lint_target = code_path
    tmp_dir = None
    if lint_source is not None:
        # Lint the *student view* (v0.13): dojo's shebang, statement docstring
        # and examples block are not the student's code, so a finding about them
        # is noise the reviewer then repeats.
        tmp_dir = tempfile.TemporaryDirectory(prefix="dojo_static_")
        lint_target = Path(tmp_dir.name) / code_path.name
        lint_target.write_text(lint_source)
    try:
        # The shebang rules are silenced (v0.10.10): even in the rare case the
        # raw file is linted, the venv shebang is dojo's chrome, not user code.
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "ruff",
                "check",
                "--output-format=json",
                # The cache belongs to dojo, not to whatever directory the CLI
                # happened to be started in: without this, `make test` created
                # `.ruff_cache/` in the repo root (v0.13 audit, S2.25).
                "--cache-dir",
                str(LOGS_DIR / "ruff"),
                "--ignore",
                "EXE001,EXE002,EXE004",
                str(lint_target),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if proc.stdout.strip():
            for finding in json.loads(proc.stdout):
                location = finding.get("location") or {}
                report.ruff.append(
                    {
                        "code": finding.get("code", "?"),
                        "message": finding.get("message", ""),
                        "line": location.get("row", 0),
                    }
                )
        elif proc.returncode != 0 and proc.stderr.strip():
            report.notes.append(f"ruff: {proc.stderr.strip()[:200]}")
    except Exception as exc:  # noqa: BLE001
        report.notes.append(f"ruff skipped: {exc}")
    finally:
        if tmp_dir is not None:
            tmp_dir.cleanup()

    return report
