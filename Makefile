# Sandbox-friendly entry points: keep uv's package cache inside the
# workspace (UV_CACHE_DIR) so builds never write outside it.
UV = UV_CACHE_DIR=$(CURDIR)/.uv-cache uv

.PHONY: sync test seed demo day version

#: Keep pyproject.toml's version in step with the git history (rule 10 in
#: AGENTS.md): writes the version the *next commit* will have. Run it as part of
#: preparing any commit; `tests/test_version.py` fails when the file drifts.
version: ## write the version this commit will have into pyproject.toml
	@$(UV) run python -c "from dojo.version import sync_pyproject as sync; v, changed = sync(); print(f'{v} — pyproject.toml ' + ('updated' if changed else 'already in step'))"


sync: ## install deps + editable dojo (incl. dev group for pytest)
	$(UV) sync --group dev

test: ## run the full test suite (offline, mock AI backend)
	$(UV) run python -m pytest -q

seed: ## scripted first-run setup (no key prompt, no PATH step)
	$(UV) run dojo setup --user andy --skip-key --no-path

demo: ## offline end-to-end demo on valid_parentheses
	DOJO_AI_BACKEND=mock $(UV) run dojo day valid_parentheses

day: ## start a real session, e.g. `make day SLUG=valid_parentheses`
	$(UV) run dojo day $(SLUG)
