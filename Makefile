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

PYTHON       ?= python3.13
VENV_DIR     ?= .venv
PIP_FLAGS    ?=
NODE_DIR     ?= frontend
API_DIR      ?= core/pioreactor/web
CORE_DIR     ?= core

# environment variables expected to come from .envrc or elsewhere
ENV_REQUIRED ?= GLOBAL_CONFIG DOT_PIOREACTOR RUN_PIOREACTOR PLUGINS_DEV PIO_EXECUTABLE PIOS_EXECUTABLE HARDWARE FIRMWARE BLINKA_FORCECHIP BLINKA_FORCEBOARD MODEL_NAME MODEL_VERSION

# --- internal helpers ---------------------------------------------------------
ACTIVATE = . $(VENV_DIR)/bin/activate
define newline


endef

# --- meta ---------------------------------------------------------------------
.PHONY: help
help:  ## Show this message
	@-$(MAKE) --no-print-directory check-env
	@awk -F':.*?## ' '/^[a-zA-Z0-9_-]+:.*?## /{printf " \033[36m%-18s\033[0m %s\n",$$1,$$2}' $(MAKEFILE_LIST)

.PHONY: check-env
check-env:  ## Verify required environment variables are loaded
	@if [ ! -f .envrc ]; then \
		echo ".envrc not found - skipping environment verification."; \
		exit 0; \
	fi; \
	missing=""; \
	for var in $(ENV_REQUIRED); do \
		if ! printenv $$var >/dev/null 2>&1; then \
			missing="$$missing $$var"; \
		fi; \
	done; \
	if [ -n "$$missing" ]; then \
		echo "Missing environment variables:"; \
		for var in $$missing; do \
			echo "  - $$var"; \
		done; \
		echo "Run 'direnv allow' (or equivalent) to load variables from .envrc"; \
		exit 1; \
	else \
		echo "All required environment variables are present."; \
	fi

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

precommit: venv ## Run pre-commit on all files
	@$(ACTIVATE) && pre-commit run --all-files

# --- test ---------------------------------------------------------------------
test: venv  ## Run all pytest suites
	@$(ACTIVATE) && pytest --rootdir=. $(CORE_DIR)/tests --timeout 300 --random-order --durations 15  --random-order-bucket=module -vv

fast-test: venv  ## Run an optimized, low-threshold test suite
	@$(ACTIVATE) && pytest --rootdir=. $(CORE_DIR)/tests --timeout 300 --random-order --durations 15  --random-order-bucket=module -vv -m "not slow and not flakey and not xfail and not skip"

slow-test: venv
	@$(ACTIVATE) && pytest --rootdir=. $(CORE_DIR)/tests --timeout 300 --random-order --durations 15  --random-order-bucket=module -vv -m slow

flakey-test: venv
	@$(ACTIVATE) && pytest --rootdir=. $(CORE_DIR)/tests --timeout 300 --random-order --durations 15  --random-order-bucket=module -vv -m "flakey or xfail or skip"

core-test: venv  ## Backend tests only
	@$(ACTIVATE) && pytest --rootdir=. $(CORE_DIR)/tests --timeout 300 --random-order --durations 15 --random-order-bucket=module --ignore=$(CORE_DIR)/tests/web  -vv

web-test: venv  ## API (Flask) tests only
	@$(ACTIVATE) && pytest --rootdir=. $(CORE_DIR)/tests/web/ --timeout 300 --random-order --durations 15 -vv

# --- build --------------------------------------------------------------------
wheel: venv  ## Build core wheel (stage 1 artifact)
	cd $(CORE_DIR) && $(ACTIVATE) && python -m build

frontend-build:
	cd $(NODE_DIR) && npm run build

# --- live dev servers ---------------------------------------------------------
web-dev: venv  ## Run Flask API on 127.0.0.1:5000
	@FLASK_ENV=development $(ACTIVATE) && cd $(API_DIR) && python3 -m flask --app app run -p 4999 --debug

frontend-dev:  ## Run React dev server on :3000
	cd $(NODE_DIR) && npm start

dev-status:  ## Show whether the usual dev services are already running
	@scripts/dev_services_status.sh

# --- background task queue ----------------------------------------------------
huey-dev: venv  ## Run the Huey consumer with sensible dev flags
	@$(ACTIVATE) && cd $(API_DIR) && \
	huey_consumer pioreactor.web.tasks.huey -n -w 10 -f -C -d 0.01

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


# --- release helpers ----------------------------------------------------------
.PHONY: create-release create-rc
create-release:  ## Perform production release workflow; pass args via ARGS="--dry-run"
	@$(PYTHON) scripts/create_release.py $(ARGS)

create-rc:  ## Create release-candidate; pass args via ARGS="--dry-run --rc 1"
	@$(PYTHON) scripts/create_rc.py $(ARGS)


# default target ---------------------------------------------------------------
.DEFAULT_GOAL := help
