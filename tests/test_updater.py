"""Updater (v0.10.1): offline tests over an injected command runner."""

from types import SimpleNamespace

from dojo.updater import update_dojo


def _script(routes: dict):
    """A fake runner: routes map the command's first word to
    (returncode, stdout, stderr). Records the commands it saw."""

    def run(cmd, timeout=30):
        routes["_calls"].append((cmd, timeout))
        key = cmd[0]
        rc, out, err = routes.get(key, (1, "", f"no route for {cmd}"))
        return SimpleNamespace(returncode=rc, stdout=out, stderr=err)

    return run


def _base_routes():
    return {
        "git": (0, "", ""),
        "uv": (0, "", ""),
        "_calls": [],
    }


def test_already_up_to_date_does_nothing():
    routes = _base_routes()
    routes["git"] = (0, "", "")
    out = update_dojo(run=_script(routes))
    assert out == "already up to date"
    assert [c[0] for c in routes["_calls"]] == [
        ["git", "status", "--porcelain"],
        ["git", "fetch", "origin"],
        ["git", "rev-parse", "HEAD"],
        ["git", "rev-parse", "@{upstream}"],
    ]
    assert not any(c[0][0] == "uv" for c in routes["_calls"])  # no sync when current


def test_pulls_and_refreshes_deps():
    calls = []
    state = {"merged": False}

    def run(cmd, timeout=30):
        calls.append(cmd)
        if cmd[0] == "git":
            if cmd[1] == "status":
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            if cmd[1] == "fetch":
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            if cmd[1] == "rev-parse":
                if cmd[2] == "HEAD":
                    head = "bbb222" if state["merged"] else "aaa111"
                else:
                    head = "bbb222"
                return SimpleNamespace(returncode=0, stdout=head, stderr="")
            if cmd[1] == "merge":
                state["merged"] = True
                return SimpleNamespace(returncode=0, stdout="", stderr="")
        if cmd[0] == "uv":
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=1, stdout="", stderr="")

    out = update_dojo(run=run)
    assert out == "updated to bbb222"
    assert ["git", "merge", "--ff-only", "bbb222"] in calls
    assert calls[-1][0] == "uv" and calls[-1][1] == "sync"


def test_local_ahead_of_upstream_is_noop_not_update():
    """The reported 'updated to <stale hash>' bug: local contains the
    upstream commit, the ff-only merge is a no-op — report it as
    up-to-date and never refresh deps."""
    calls = []

    def run(cmd, timeout=30):
        calls.append(cmd)
        if cmd[0] == "git":
            if cmd[1] in ("status", "fetch", "merge"):
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            if cmd[1] == "rev-parse":
                return SimpleNamespace(
                    returncode=0,
                    stdout="ccc333" if cmd[2] == "HEAD" else "aaa111",
                    stderr="",
                )
        return SimpleNamespace(returncode=1, stdout="", stderr="")

    out = update_dojo(run=run)
    assert out == "already up to date"
    assert not any(c[0] == "uv" for c in calls)


def test_dirty_tree_skips_and_suggests_force():
    routes = _base_routes()
    routes["git"] = (0, "M src/dojo/cli.py\n", "")

    def run(cmd, timeout=30):
        routes["_calls"].append((cmd, timeout))
        return SimpleNamespace(returncode=0, stdout=routes["git"][1], stderr="")

    out = update_dojo(run=run)
    assert "local changes" in out and "force" in out
    assert [c[0][0] for c in routes["_calls"]] == ["git"]  # only the status ran


def test_force_discards_local_changes():
    routes = _base_routes()
    calls = routes["_calls"]
    state = {"reset": False}

    def run(cmd, timeout=30):
        calls.append((cmd, timeout))
        if cmd[0] == "git":
            if cmd[1] == "status":
                return SimpleNamespace(returncode=0, stdout="M junk\n", stderr="")
            if cmd[1] == "fetch":
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            if cmd[1] == "rev-parse":
                if cmd[2] == "HEAD":
                    head = "bbb222" if state["reset"] else "aaa111"
                else:
                    head = "bbb222"
                return SimpleNamespace(returncode=0, stdout=head, stderr="")
            if cmd[1] == "reset":
                state["reset"] = True
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    out = update_dojo(run=run, force=True)
    assert out == "updated to bbb222"
    assert any(c[0][1] == "reset" for c in calls)


def test_offline_fetch_skips():
    routes = _base_routes()
    calls = routes["_calls"]

    def run(cmd, timeout=30):
        calls.append((cmd, timeout))
        if cmd[0] == "git" and cmd[1] == "status":
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=1, stdout="", stderr="fatal: network down")

    out = update_dojo(run=run)
    assert "could not fetch" in out
    assert not any(c[0][0] == "uv" for c in calls)
