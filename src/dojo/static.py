"""Static analysis at submit (v0.4): radon cyclomatic complexity + ruff.

Evidence for the reviewer and the learner, not a verdict: complexity above
the McCabe convention (10) and lint findings are flags, never failures.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

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


def analyze(code_path: Path) -> StaticReport:
    """Cyclomatic complexity per function (radon) + lint findings (ruff).
    Never raises: broken code or tool hiccups degrade into notes."""
    report = StaticReport()
    source = code_path.read_text()

    try:
        from radon.complexity import cc_visit
        from radon.visitors import Function

        for block in cc_visit(source):
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

    try:
        proc = subprocess.run(
            [sys.executable, "-m", "ruff", "check", "--output-format=json", str(code_path)],
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

    return report
