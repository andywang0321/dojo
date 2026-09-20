"""Shared fixtures: temp DB, fake console for interactive flows.

**State isolation is a guard, not a convention (v0.13).** A full test run must
never read or write the real `data/dojo.db`, `data/logs/`, `data/dojo.conf` or
`~/.local/share/dojo/workbench`: the workbench holds live user code and the debug
log is the only record of live AI traffic. The environment is redirected to a
session-scoped temp root *before dojo is imported*, and that root is shaped so
the path assertions in `test_config.py` still describe reality. `DOJO_NO_AUTO_UPDATE`
is set for the same reason — `cli.main` would otherwise `git fetch` and touch a
real DB.
"""

from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

# The redirect must happen before any dojo module computes a path at import.
_TMP_ROOT = Path(tempfile.mkdtemp(prefix="dojo-tests-"))
#: Named so `WORKBENCH_DIR` still ends with "dojo/workbench" (test_config asserts
#: it) while staying outside REPO_ROOT (test_config asserts that too).
WORKBENCH_ROOT = _TMP_ROOT / "dojo" / "workbench"
DATA_ROOT = _TMP_ROOT / "data"
os.environ["DOJO_WORKBENCH_DIR"] = str(WORKBENCH_ROOT)
os.environ["DOJO_DATA_DIR"] = str(DATA_ROOT)
os.environ["DOJO_NO_AUTO_UPDATE"] = "1"

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

from dojo.db import init_db  # noqa: E402


@pytest.fixture(autouse=True)
def _session_paths_are_sandboxed():
    """Re-assert the redirected paths around every test.

    `tests/test_config.py` deliberately reloads `dojo.config` with
    `DOJO_WORKBENCH_DIR` unset to prove the default resolution, which leaves the
    module pointing at the real per-user directory; nothing may observe that
    state, so repair it on the way out.
    """
    from dojo import config

    yield
    if str(config.WORKBENCH_DIR) != os.environ["DOJO_WORKBENCH_DIR"]:
        importlib.reload(config)


@pytest.fixture()
def db(tmp_path):
    db_path = tmp_path / "dojo.db"
    init_db(db_path)
    from dojo.db import connect

    conn = connect(db_path)
    yield conn
    conn.close()


class FakeConsole:
    """Console stand-in: records prints, serves canned inputs.

    ``actions`` maps a canned answer to a callback fired when that answer is
    popped — the way tests simulate the user editing the workbench file
    during a session (e.g. writing the solution right before "submit")."""

    def __init__(self, answers: list[str] | None = None, actions: dict | None = None):
        self.answers = list(answers or [])
        self.actions = dict(actions or {})
        self.out: list[str] = []

    def print(self, *args, **kwargs):
        self.out.append(" ".join(str(a) for a in args))

    def input(self, prompt: str = "") -> str:
        self.out.append(str(prompt))
        if not self.answers:
            # Silently answering "quit" made under-specified tests pass while
            # exercising a path they never intended (v0.13 audit, S5.7): an
            # exhausted script is a bug in the test.
            raise AssertionError(
                f"the test ran out of canned answers at prompt: {prompt!r}"
            )
        answer = self.answers.pop(0)
        action = self.actions.get(answer)
        if action:
            action()
        return answer

    @property
    def text(self) -> str:
        return "\n".join(self.out)


@pytest.fixture()
def fake_console():
    def make(answers=None, actions=None):
        return FakeConsole(answers, actions)

    return make


@pytest.fixture()
def synthetic_probe(monkeypatch):
    """Replace the probe's *subprocess measurement* with a deterministic cost
    model, leaving everything else real (interleaving, medians, digests, failure
    propagation, the ratio series, the verdict).

    This is how a test may assert a complexity verdict at all: reading a class
    off wall-clock time is a test of the machine's load, not of the code
    (AGENTS.md rule 5 — `tests/test_flow.py` failed 33% of the time at 6-way
    concurrency exactly that way). Usage:

        synthetic_probe(lambda label, n: n)             # identical cost curves
        synthetic_probe(lambda label, n: n if label == "yours" else 1)
    """

    def install(model):
        import copy
        import hashlib
        import importlib.util
        import json

        from dojo.profiler.probe import Run

        # The probe harness injects these into the measured module's namespace
        # (it is a string constant there, so it cannot be imported); a curated
        # reference carries its own @reference("slug") line and would otherwise
        # fail to import under a synthetic measurement exactly as it would under
        # the real one.
        noop_decorators = (
            "oracle",
            "judge_case",
            "profiler_input",
            "checker",
            "reference",
        )

        def _identity_decorator(*args, **kwargs):
            def wrap(fn):
                return fn

            return wrap

        def fake_run_one(target, args, timeout=20.0, compare="strict"):
            size = sum(len(a) if isinstance(a, (list, str)) else 1 for a in args)
            spec = importlib.util.spec_from_file_location(
                f"synth_{target.label}", target.path
            )
            module = importlib.util.module_from_spec(spec)
            for name in noop_decorators:
                setattr(module, name, _identity_decorator)
            try:
                spec.loader.exec_module(module)
                got = getattr(module, target.function_name)(
                    *copy.deepcopy(args)
                )
            except BaseException as exc:  # noqa: BLE001 - mirrors the harness
                return Run(error=f"{type(exc).__name__}: {exc}")
            blob = json.dumps(got, sort_keys=True, default=str)
            return Run(
                ms=float(model(target.label, size)),
                peak=8 * size,
                digest=hashlib.sha256(blob.encode()).hexdigest(),
                preview=blob[:60],
            )

        monkeypatch.setattr("dojo.profiler.probe.run_one", fake_run_one)
        return model

    return install


@pytest.fixture()
def cli_env(tmp_path, monkeypatch):
    """Drive `cli.main` end to end against a temp DB and workbench.

    Product-level tests (the muscle the suite was missing — 10 of 17 `_cmd_*`
    handlers had no caller and `main()` appeared once, with help argv) need three
    things patched that the module-level constants make patchable: the DB path,
    the seed corpus, and the workbench. Interactive input is answered from a
    canned list through `Console.input`; `Console.print` is captured verbatim.
    """
    from rich.console import Console

    from dojo import cli as cli_mod
    from dojo.config import PROBLEMS_DIR

    monkeypatch.setenv("DOJO_AI_BACKEND", "mock")
    db_path = tmp_path / "cli.db"
    workbench = tmp_path / "workbench"
    workbench.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(cli_mod, "DB_PATH", db_path)
    monkeypatch.setattr(cli_mod, "WORKBENCH_DIR", workbench)
    monkeypatch.setattr(
        "dojo.session.flow.WORKBENCH_DIR", workbench, raising=False
    )
    monkeypatch.setattr(
        "dojo.session.state.WORKBENCH_DIR", workbench, raising=False
    )
    init_db(db_path)

    class Recorder:
        def __init__(self):
            self.out: list[str] = []
            self.answers: list[str] = []

        @property
        def text(self) -> str:
            return "\n".join(self.out)

    rec = Recorder()

    original_print = Console.print  # captured before the patch below

    def render(value) -> str:
        """Strings verbatim; rich renderables through a real Console capture.

        Without this a table records as `<rich.table.Table object at 0x…>` and
        every assertion about output becomes unfalsifiable — the failure mode
        `FakeConsole` already has. The *original* `Console.print` is used, since
        the class method is patched below (calling through `print` here would
        recurse forever)."""
        if isinstance(value, str):
            return value
        import io as _io

        from rich.console import Console as _Console

        capture_console = _Console(file=_io.StringIO(), width=200)
        original_print(capture_console, value)
        return capture_console.file.getvalue()

    def fake_print(self, *args, **kwargs):  # noqa: ANN001 - rich Console method
        rec.out.append(" ".join(render(a) for a in args))

    def fake_input(self, prompt="", **kwargs):  # noqa: ANN001
        rec.out.append(str(prompt))
        return rec.answers.pop(0) if rec.answers else "quit"

    monkeypatch.setattr("rich.console.Console.print", fake_print)
    monkeypatch.setattr("rich.console.Console.input", fake_input)
    return rec, db_path, workbench, PROBLEMS_DIR
