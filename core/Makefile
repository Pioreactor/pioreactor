
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

# GitHub CLI

gh-open: ## Open the GitHub repository in the browser
	@gh repo view pioreactor/pioreactor --web

gh-issues: ## List GitHub issues for the repository
	@gh issue list --repo pioreactor/pioreactor

gh-prs: ## List open pull requests for the repository
	@gh pr list --repo pioreactor/pioreactor

gh-pr: ## Create a new pull request. Additional args passed to gh.
	@gh pr create --repo pioreactor/pioreactor $(ARGS)

gh-workflows: ## List GitHub Actions workflows for the repository
	@gh workflow list --repo pioreactor/pioreactor

gh-run-workflow: ## Run a GitHub Actions workflow. Usage: make gh-run-workflow WORKFLOW=<workflow file> [ARGS]
	@gh workflow run $(WORKFLOW) --repo pioreactor/pioreactor $(ARGS)
