"""Config paths (v0.10.1): the workbench lives outside the repo."""

import os


def test_workbench_lives_outside_repo():
    from dojo.config import REPO_ROOT, WORKBENCH_DIR

    assert REPO_ROOT not in WORKBENCH_DIR.parents
    assert str(WORKBENCH_DIR).endswith("dojo/workbench")


def test_workbench_env_override(monkeypatch):
    import importlib

    from dojo import config

    monkeypatch.setenv("DOJO_WORKBENCH_DIR", "/tmp/custom-workbench")
    importlib.reload(config)
    try:
        assert str(config.WORKBENCH_DIR) == "/tmp/custom-workbench"
    finally:
        monkeypatch.delenv("DOJO_WORKBENCH_DIR", raising=False)
        importlib.reload(config)
    assert "/tmp/custom-workbench" not in str(config.WORKBENCH_DIR)
    assert os.environ.get("DOJO_WORKBENCH_DIR") is None
