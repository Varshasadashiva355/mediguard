# MediGuard AI – Makefile
# Intelligent Cardiac Monitoring. Smarter Clinical Decisions.

.PHONY: help setup seed test test-e2e test-rls run-backend run-worker run clean

PYTHON = .venv/Scripts/python
PYTEST = .venv/Scripts/pytest

help:
	@echo "Available commands:"
	@echo "  make setup         - Create virtualenv and install all dependencies"
	@echo "  make seed          - Seed synthetic users, 30 patients, and ECG reports"
	@echo "  make test          - Run full pytest test suite"
	@echo "  make test-e2e      - Run end-to-end clinical lifecycle smoke test"
	@echo "  make test-rls      - Run 12-check Row Level Security & RBAC verification"
	@echo "  make run-backend   - Start Flask REST API server on port 5000"
	@echo "  make run-worker    - Start background ECG inference worker"
	@echo "  make run           - Run both backend and worker concurrently"

setup:
	python -m venv .venv
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

seed:
	$(PYTHON) -m backend.db.cli seed

test:
	$(PYTEST) tests/ -v

test-e2e:
	$(PYTEST) tests/test_e2e_smoke.py -v

test-rls:
	$(PYTHON) -m scripts.rls_verify

run-backend:
	$(PYTHON) -m backend.app

run-worker:
	$(PYTHON) -m backend.worker.worker --interval 1.0

run:
	@echo "Starting MediGuard AI Backend and Background Worker..."
	start cmd /k "$(PYTHON) -m backend.app"
	start cmd /k "$(PYTHON) -m backend.worker.worker --interval 1.0"
