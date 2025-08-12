# ──────────────────────────────────────────────────────────
# Pioreactor mono-repo – development helpers (stage 1)
#  * Python 3.11   (core + Flask API)
#  * Node 20       (React frontend)
#  * Docker        (optional dev stack: mosquitto, sqlite viewer, etc.)
#
# USAGE:  make <target>
# List targets:  make help
# ──────────────────────────────────────────────────────────

# --- configurable knobs -------------------------------------------------------

PYTHON       ?= python3.11        # put full path if multiple versions
VENV_DIR     ?= .venv
PIP_FLAGS    ?=
NODE_DIR     ?= frontend
API_DIR      ?= web
CORE_DIR  ?= core

# --- internal helpers ---------------------------------------------------------
ACTIVATE = . $(VENV_DIR)/bin/activate
define newline


endef

# --- meta ---------------------------------------------------------------------
.PHONY: help
help:  ## Show this message
	@awk -F':.*?## ' '/^[a-zA-Z0-9_-]+:.*?## /{printf " \033[36m%-18s\033[0m %s\n",$$1,$$2}' $(MAKEFILE_LIST)

# --- environment --------------------------------------------------------------
$(VENV_DIR)/bin/activate:  ## Create virtual env + core tooling
	@echo ">> Creating virtual env in $(VENV_DIR)"
	@$(PYTHON) -m venv $(VENV_DIR)
	@$(ACTIVATE) && pip install -U pip wheel $(PIP_FLAGS)$(newline)
	@touch $@

venv: $(VENV_DIR)/bin/activate  ## Alias – ensure venv exists

install: venv  ## Install *all* python dependencies
	@$(ACTIVATE) && pip install -r requirements/requirements_dev.txt -r requirements/requirements.txt  -e core/ $(PIP_FLAGS)

node_modules/.installed: $(NODE_DIR)/package.json  ## Install Node deps
	cd $(NODE_DIR) && npm ci
	@date > $@

frontend-install: node_modules/.installed ## Alias

# --- quality gates ------------------------------------------------------------
lint: venv  ## Run ruff & black in check-only mode
	@$(ACTIVATE) && ruff check $(CORE_DIR) $(API_DIR)
	@$(ACTIVATE) && black --check $(CORE_DIR) $(API_DIR)

format: venv  ## Reformat python code with black
	@$(ACTIVATE) && black $(CORE_DIR) $(API_DIR)

precommit: venv ## Run pre-commit on all files
	@$(ACTIVATE) && pre-commit run --all-files

# --- test ---------------------------------------------------------------------
test: venv  ## Run all pytest suites
	@$(ACTIVATE) && pytest $(CORE_DIR)/tests $(API_DIR)/tests --timeout 600 --random-order --durations 15

core-test: venv  ## Backend tests only
	@$(ACTIVATE) && pytest $(CORE_DIR)/tests --timeout 600 --random-order --durations 15

web-test: venv  ## API (Flask) tests only
	@$(ACTIVATE) && pytest $(API_DIR)/tests --timeout 600 --random-order --durations 15

# --- build --------------------------------------------------------------------
wheel: venv  ## Build core wheel (stage 1 artifact)
	cd $(CORE_DIR) && $(ACTIVATE) && python -m build

frontend-build:
	cd $(NODE_DIR) && npm run build

# --- live dev servers ---------------------------------------------------------
web-dev: venv  ## Run Flask API on 127.0.0.1:5000
	@FLASK_ENV=development $(ACTIVATE) && cd $(API_DIR) && python3 -m flask  --app main run -p 4999 --debug

frontend-dev:  ## Run React dev server on :3000
	cd $(NODE_DIR) && npm start

# --- background task queue ----------------------------------------------------
huey-dev: venv  ## Run the Huey consumer with sensible dev flags
	@$(ACTIVATE) && cd $(API_DIR) && \
	huey_consumer pioreactorui.tasks.huey -n -b 1.001 -w 10 -f -C -d 0.05

# --- clean-up -----------------------------------------------------------------
clean:  ## Delete bytecode, build artefacts, node deps
	rm -rf $(VENV_DIR) dist/ build/ *.egg-info
	find . -name '__pycache__' -exec rm -rf {} +
	rm -rf $(NODE_DIR)/build node_modules .pytest_cache

reinstall: clean install frontend-install  ## Freshen everything


# --- logs ---------------------------------------------------------------------
LOG_FILE ?= pioreactor.log   # change if you ever relocate the master log
LINES    ?= 10              # default lines to display


tail-log:  ## Show last $$LINES lines of the merged pioreactor log (override with LINES=200)
	@echo "┏━ $(LOG_FILE) (last $(LINES) lines) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@tail -n $(LINES) $(LOG_FILE)


# default target ---------------------------------------------------------------
.DEFAULT_GOAL := help

# --- release helpers ----------------------------------------------------------
.PHONY: rc
rc: ## Create a release candidate (ARGS="--dry-run" to preview)
	@$(PYTHON) scratch/create_rc.py $(ARGS)
