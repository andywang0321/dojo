"""Judge + profiler robustness (v0.10.1): user prints, sys.exit, and
import-time prints must never crash dojo or corrupt the protocol channel."""

import textwrap

from dojo.judge import run_cases
from dojo.profiler import probe as probe_mod

CASES = [
    {"args": [3], "expected": 6, "label": "a"},
    {"args": [4], "expected": 8, "label": "b"},
]


def _judge(code: str):
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "solution.py"
        path.write_text(textwrap.dedent(code))
        return run_cases(path, "double", CASES)


def test_print_in_solution_does_not_corrupt_judge():
    report = _judge(
        """
        def double(n):
            print("debug: doubling", n)
            return n * 2
        """
    )
    assert report.status == "correct", report.results
    assert report.passed == 2
    printed = "\n".join(r.printed for r in report.results)
    assert "debug: doubling 3" in printed  # prints are captured, not discarded


def test_import_time_print_does_not_corrupt_judge():
    report = _judge(
        """
        print("module loaded")

        def double(n):
            return n * 2
        """
    )
    assert report.status == "correct", report.results


def test_sys_exit_is_a_case_error_not_a_crash():
    report = _judge(
        """
        import sys

        def double(n):
            if n == 4:
                sys.exit("boom")
            return n * 2
        """
    )
    assert report.status == "error"  # a case-level exception (v0.13), not a mismatch
    results = {r.label: r for r in report.results}
    assert results["a"].passed is True
    assert "SystemExit" in results["b"].error


def test_print_in_solution_does_not_corrupt_measurement(tmp_path):
    path = tmp_path / "solution.py"
    path.write_text(
        textwrap.dedent(
            """
            def double(n):
                print("debug print from the measured function")
                return n * 2
            """
        )
    )
    result = probe_mod.run_probe(
        probe_mod.Target("yours", path, "double"),
        lambda n, rng: [n],
        sizes=[100, 200, 400],
        repeats=1,
    )
    # Prints go to stderr inside the probe harness, so the JSON channel stays
    # intact and every size still measures.
    assert [p.n for p in result.points] == [100, 200, 400]
    assert all(p.student.ok and p.student.ms > 0 for p in result.points)


# ------------------------------------------------ hostile-output hardening (v0.13)
# Each test below pins a defect that was reproduced against the v0.12 judge: a
# session-ending traceback, a machine-filling print loop, an orphaned grandchild,
# and a free pass on an empty case list.


def test_fd_level_write_does_not_corrupt_the_protocol():
    """`os.write(1, …)` bypassed the `sys.stdout` swap and corrupted the result
    JSON, which then raised out of `run_cases` and killed the session."""
    report = _judge(
        """
        import os

        def double(n):
            os.write(1, b"raw fd output\\n")
            return n * 2
        """
    )
    assert report.status == "correct", report.results
    assert report.passed == 2
    assert "raw fd output" in "\n".join(r.printed for r in report.results)


def test_a_child_process_print_does_not_corrupt_the_protocol():
    """A spawned process inherits fd 1 — the same channel the protocol uses."""
    report = _judge(
        """
        import subprocess

        def double(n):
            subprocess.run(["/bin/echo", "child noise"])
            return n * 2
        """
    )
    assert report.status == "correct", report.results


def test_print_from_a_background_thread_does_not_corrupt_the_protocol():
    report = _judge(
        """
        import threading, time

        def double(n):
            threading.Thread(target=lambda: (time.sleep(0.05), print("late"))).start()
            time.sleep(0.15)
            return n * 2
        """
    )
    assert report.status == "correct", report.results


def test_an_atexit_print_after_the_result_is_ignored():
    """The parent reads the last parseable line, so output that lands *after*
    the result cannot invalidate it."""
    report = _judge(
        """
        import atexit

        atexit.register(lambda: print("goodbye from atexit"))

        def double(n):
            return n * 2
        """
    )
    assert report.status == "correct", report.results


def test_printed_output_survives_a_crashing_case():
    """Prints are the debugging loop, so a case that raises must still report
    what it printed — the old handler hard-coded `printed: ""`."""
    report = _judge(
        """
        def double(n):
            print("about to fail with", n)
            raise ValueError("boom")
        """
    )
    assert report.status == "error"
    assert "about to fail with 3" in report.results[0].printed


def test_printed_output_is_capped_while_it_is_written():
    """The cap used to apply *after* the whole output existed in a StringIO, so
    it bounded what was shown and nothing else: a print loop reached ~1.9 GB RSS
    in three seconds. The writer now stops growing at the cap."""
    report = _judge(
        """
        def double(n):
            for _ in range(200_000):
                print("x" * 100)  # ~20 MB if nothing stops it
            return n * 2
        """
    )
    assert report.status == "correct", report.results
    printed = report.results[0].printed
    assert len(printed) < 20000
    assert "truncated" in printed  # and it says so, rather than lying by omission


def test_a_runaway_print_loop_cannot_take_the_machine_down(tmp_path):
    """A loop that never stops printing must come back as a *report*: the child
    is bounded by the fd/output caps and, failing that, by the timeout."""
    solution = tmp_path / "solution.py"
    solution.write_text("def double(n):\n    while True:\n        print('x' * 1000)\n")
    report = run_cases(solution, "double", CASES, timeout=1.5)
    assert report.status in ("error", "timed_out")


def test_an_empty_case_list_is_refused_not_passed():
    """`all_passed` is true for zero cases, which made a problem with no visible
    tests and no generator a free solve."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "solution.py"
        path.write_text("def double(n):\n    raise NotImplementedError\n")
        report = run_cases(path, "double", [])
    assert report.status == "error"
    assert report.passed == 0
    assert not report.all_passed
    assert "no cases" in report.results[0].label


def test_a_timeout_kills_the_whole_process_group(tmp_path):
    """`subprocess.run(timeout=…)` kills only the direct child: a spawned
    grandchild survived the run."""
    import os
    import signal
    import time

    marker_pid = tmp_path / "child.pid"
    solution = tmp_path / "solution.py"
    solution.write_text(
        textwrap.dedent(
            f"""
            import subprocess, time, pathlib

            def double(n):
                proc = subprocess.Popen(["/bin/sleep", "60"])
                pathlib.Path({str(marker_pid)!r}).write_text(str(proc.pid))
                time.sleep(60)
            """
        )
    )
    report = run_cases(solution, "double", CASES, timeout=2.0)
    assert report.status == "timed_out"
    deadline = time.time() + 5
    while not marker_pid.exists() and time.time() < deadline:
        time.sleep(0.05)
    if marker_pid.exists():
        pid = int(marker_pid.read_text())
        # The whole group must be gone: signal 0 probes for existence.
        gone = False
        for _ in range(40):
            try:
                os.kill(pid, 0)
            except (ProcessLookupError, PermissionError):
                gone = True
                break
            time.sleep(0.05)
        if not gone:  # clean up before failing, never leak the process
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        assert gone, "a grandchild outlived the timed-out run"


def test_a_malformed_case_is_isolated(tmp_path):
    """`case["expected"]` was read outside the per-case try, so one malformed
    case destroyed every other case's result."""
    solution = tmp_path / "solution.py"
    solution.write_text("def double(n):\n    return n * 2\n")
    report = run_cases(
        solution,
        "double",
        [{"args": [3], "expected": 6, "label": "ok"}, {"args": [4], "label": "bad"}],
    )
    assert report.status == "error"
    labels = {r.label for r in report.results}
    assert "ok" in labels and "bad" in labels
    assert {r.label: r.passed for r in report.results}["ok"] is True


def test_the_runner_seam_accepts_another_interpreter(tmp_path):
    """`python=` is the seam a second curriculum needs (JAX gets its own venv;
    Rust gets a different harness entirely)."""
    import sys

    solution = tmp_path / "solution.py"
    solution.write_text("def double(n):\n    return n * 2\n")
    report = run_cases(solution, "double", CASES, python=sys.executable)
    assert report.status == "correct"
