
.DEFAULT_GOAL := help

help: ## Show this help.
	@printf "\nUsage:\n"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z0-9_-]+:.*?## / { printf "  %-20s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

# --- logs ---------------------------------------------------------------------
LOG_FILE ?= ../pioreactor.log   # change if you ever relocate the master log
LINES    ?= 10              # default lines to display


tail-log:  ## Show last $$LINES lines of the merged pioreactor log (override with LINES=200)
	@echo "┏━ $(LOG_FILE) (last $(LINES) lines) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@tail -n $(LINES) $(LOG_FILE)

tail-mqtt: ## Tail mosquitto
	@mosquitto_sub -t "#" -v -F "%19.19I  |  %t   %p"

install: ## Install package in editable mode
	@pip install -e .

install-dev: ## Install development dependencies
	@pip install -r requirements/requirements_dev.txt

test: ## Run test suite
	@python3 -m pytest

type-check: ## Run mypy
	@mypy pioreactor
