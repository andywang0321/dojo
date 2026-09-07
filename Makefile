# Sandbox-friendly entry points: keep uv's package cache inside the
# workspace (UV_CACHE_DIR) so builds never write outside it.
UV = UV_CACHE_DIR=$(CURDIR)/.uv-cache uv

.PHONY: sync test seed demo day

sync: ## install deps + editable dojo
	$(UV) sync

test: ## run the full test suite (offline, mock AI backend)
	$(UV) run pytest -q

seed: ## create DB and seed the problem bank from dsa/
	$(UV) run dojo init --user andy

demo: ## offline end-to-end demo on valid_parentheses
	DOJO_AI_BACKEND=mock $(UV) run dojo day valid_parentheses --user andy

day: ## start a real session, e.g. `make day SLUG=valid_parentheses USER=andy`
	$(UV) run dojo day $(SLUG) --user $(USER)
