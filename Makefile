.PHONY: help install install-dev clean test test-coverage lint format type-check security-check build docker-build run-example all ci

# Default target
.DEFAULT_GOAL := help

# Python interpreter
PYTHON := python3
PIP := $(PYTHON) -m pip

# Project directories
SRC_DIR := cassandra_analyzer
TEST_DIR := tests
SCRIPTS_DIR := scripts

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
RED := \033[0;31m
YELLOW := \033[0;33m
NC := \033[0m # No Color

help: ## Show this help message
	@echo "$(BLUE)Cassandra Analyzer - Development Commands$(NC)"
	@echo ""
	@echo "$(GREEN)Available targets:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(GREEN)Quick start:$(NC)"
	@echo "  $$ make install-dev    # Install with development dependencies"
	@echo "  $$ make test          # Run tests"
	@echo "  $$ make lint          # Check code style"
	@echo "  $$ make run-example   # Run with example config"

install: ## Install production dependencies
	$(PIP) install --upgrade pip setuptools wheel
	$(PIP) install -r requirements.txt
	$(PIP) install -e .

install-dev: ## Install development dependencies
	$(PIP) install --upgrade pip setuptools wheel
	$(PIP) install -r requirements.txt
	$(PIP) install -r requirements-dev.txt
	$(PIP) install -e .
	pre-commit install

clean: ## Clean build artifacts and cache files
	find . -type f -name '*.pyc' -delete
	find . -type d -name '__pycache__' -delete
	find . -type d -name '*.egg-info' -exec rm -rf {} + 2>/dev/null || true
	rm -rf build/ dist/ .coverage htmlcov/ .pytest_cache/ .mypy_cache/ .tox/
	rm -f coverage.xml

test: ## Run unit tests
	pytest $(TEST_DIR) -v

test-coverage: ## Run tests with coverage report
	pytest $(TEST_DIR) -v --cov=$(SRC_DIR) --cov-report=html --cov-report=term --cov-report=xml

test-watch: ## Run tests in watch mode
	pytest-watch $(TEST_DIR) -v

lint: ## Run all linters
	@echo "$(BLUE)Running flake8...$(NC)"
	flake8 --config=.flake8 $(SRC_DIR) $(TEST_DIR)
	@echo "$(YELLOW)Skipping black and isort checks to avoid source code changes$(NC)"
	@echo "$(GREEN)Flake8 checks passed!$(NC)"

format: ## Format code with black and isort
	@echo "$(BLUE)Formatting with black...$(NC)"
	black $(SRC_DIR) $(TEST_DIR)
	@echo "$(BLUE)Sorting imports with isort...$(NC)"
	isort $(SRC_DIR) $(TEST_DIR)
	@echo "$(GREEN)Code formatted!$(NC)"

type-check: ## Run type checking with mypy
	mypy $(SRC_DIR) --ignore-missing-imports

security-check: ## Run security checks with bandit
	bandit -r $(SRC_DIR) -ll

build: clean ## Build distribution packages
	$(PYTHON) -m build

build-exe: clean ## Build standalone executable using PyInstaller
	@echo "$(BLUE)Building standalone executable...$(NC)"
	pyinstaller cassandra-analyzer.spec --clean
	@echo "$(GREEN)Executable built successfully in dist/$(NC)"

build-exe-onedir: clean ## Build executable in one-folder mode (for debugging)
	@echo "$(BLUE)Building executable in one-folder mode...$(NC)"
	pyinstaller cassandra-analyzer.spec --onedir --clean
	@echo "$(GREEN)Executable built successfully in dist/$(NC)"

build-all-exe: ## Build executables for all platforms (requires appropriate environment)
	@echo "$(BLUE)Building executables for all platforms...$(NC)"
	@echo "$(YELLOW)Note: Cross-platform builds require appropriate build environments$(NC)"
	make build-exe
	@echo "$(GREEN)Build complete for current platform$(NC)"

docker-build: ## Build Docker image
	docker build -t cassandra-analyzer:latest .

docker-run: ## Run Docker container with example config
	docker run -v $(PWD)/example_config.yaml:/config.yaml:ro \
		-v $(PWD)/reports:/home/analyzer/reports \
		cassandra-analyzer:latest --config /config.yaml

run-example: ## Run analyzer with example configuration
	$(PYTHON) -m cassandra_analyzer --config example_config.yaml --verbose

license-headers: ## Add Apache license headers to Python files
	$(PYTHON) $(SCRIPTS_DIR)/add_license_headers.py

pre-commit: ## Run pre-commit hooks on all files
	pre-commit run --all-files

ci: lint type-check security-check test-coverage ## Run all CI checks locally

all: clean install-dev ci build ## Run full build pipeline

# Development workflow commands
dev-setup: install-dev ## Complete development environment setup
	@echo "$(GREEN)Development environment ready!$(NC)"
	@echo "Run 'make test' to run tests"
	@echo "Run 'make lint' to check code style"
	@echo "Run 'make run-example' to test the analyzer"

update-deps: ## Update all dependencies to latest versions
	$(PIP) install --upgrade pip-tools
	pip-compile --upgrade requirements.in -o requirements.txt
	pip-compile --upgrade requirements-dev.in -o requirements-dev.txt

# Tox commands for testing multiple Python versions
tox: ## Run tests on multiple Python versions using tox
	tox

tox-recreate: ## Recreate tox environments
	tox -r