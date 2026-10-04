# Makefile for Rain Corrector
#
# Provides targets to run the backend, run the frontend,
# execute containerized Docker services, run ML pipelines, and execute tests.

SHELL := /bin/bash
PYTHON_BACKEND := backend/.venv/bin/python
PYTHON_ML := ml/.venv/bin/python
UVICORN := backend/.venv/bin/uvicorn
ALEMBIC := backend/.venv/bin/alembic
PYTEST_BACKEND := backend/.venv/bin/pytest
PYTEST_ML := ml/.venv/bin/pytest

.PHONY: help setup db migrate run-backend backend run-frontend frontend \
        docker docker-up docker-down docker-logs docker-restart \
        download-data validate-data preprocess train evaluate predict seed \
        test test-backend test-ml test-frontend build-frontend clean

# Default target
.DEFAULT_GOAL := help

help:
	@echo "========================================================================"
	@echo "Rain Corrector - Project Automation Commands"
	@echo "========================================================================"
	@echo "Application Run Targets:"
	@echo "  make run-backend     - Run the FastAPI backend server (http://localhost:8000)"
	@echo "  make run-frontend    - Run the Next.js frontend dev server (http://localhost:3000)"
	@echo "  make backend         - Alias for run-backend"
	@echo "  make frontend        - Alias for run-frontend"
	@echo "  make db              - Start PostgreSQL container (port 55432)"
	@echo ""
	@echo "Containerized Docker Targets:"
	@echo "  make docker-up       - Build & start all containerized services (DB, backend, frontend)"
	@echo "  make docker-down     - Stop containerized application services"
	@echo "  make docker          - Alias for docker-up"
	@echo "  make docker-logs     - Tail logs of running Docker containers"
	@echo "  make docker-restart  - Restart containerized services"
	@echo ""
	@echo "Data Pipeline & ML Targets:"
	@echo "  make download-data   - Download authoritative CWC/CPCB telemetry datasets"
	@echo "  make validate-data   - Validate datasets and verify storage budget (<= 1 GB)"
	@echo "  make preprocess      - Clean telemetry & build zero-leakage feature tables"
	@echo "  make train           - Train models on real observations and promote candidate"
	@echo "  make evaluate        - Evaluate holdout metrics (MAE, RMSE, NSE, POD, FAR, CSI)"
	@echo "  make predict         - Run CLI prediction for sample districts (e.g. Nashik, Jalgaon)"
	@echo "  make seed            - Seed PostgreSQL with observations & backfill forecast runs"
	@echo ""
	@echo "Setup, Migrations & Tests:"
	@echo "  make setup           - Run initial setup script (virtualenvs, dependencies, migrations)"
	@echo "  make migrate         - Apply Alembic database migrations"
	@echo "  make test            - Run all test suites (ML, Backend, Frontend)"
	@echo "  make test-backend    - Run backend API & integration tests"
	@echo "  make test-ml         - Run ML pipeline and real data tests"
	@echo "  make test-frontend   - Run frontend vitest suite"
	@echo "  make build-frontend  - Build production Next.js frontend bundle"
	@echo "  make clean           - Clean temporary cache files"
	@echo "========================================================================"

# --- Local Application Run Targets ---

run-backend: db
	@echo "Starting FastAPI backend server on http://localhost:8000..."
	@cd backend && .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

backend: run-backend

run-frontend:
	@echo "Starting Next.js frontend on http://localhost:3000..."
	@cd frontend && npm run dev

frontend: run-frontend

db:
	@if [ "$$(docker ps -q -f name=rain_corrector_db)" ]; then \
		echo "PostgreSQL container is already running on port 55432."; \
	elif [ "$$(docker ps -aq -f name=rain_corrector_db)" ]; then \
		echo "Starting existing PostgreSQL container..."; \
		docker start rain_corrector_db; \
	else \
		echo "Starting PostgreSQL container via Docker Compose..."; \
		docker compose up -d db; \
	fi

# --- Containerized Docker Targets ---

docker-up:
	@echo "Starting containerized database and application stack..."
	@docker compose up -d db
	@docker compose --profile app up --build -d
	@echo ""
	@echo "Containerized stack is running:"
	@echo "  - Backend API: http://localhost:8000"
	@echo "  - Frontend UI: http://localhost:3000"
	@echo "  - PostgreSQL:  localhost:55432"

docker: docker-up

docker-down:
	@echo "Stopping containerized application services..."
	@docker compose --profile app down

docker-logs:
	@docker compose --profile app logs -f

docker-restart: docker-down docker-up

# --- Setup & Database Migrations ---

setup:
	@./scripts/setup.sh

migrate:
	@echo "Applying Alembic database migrations..."
	@$(ALEMBIC) -c database/alembic.ini upgrade head

seed:
	@echo "Seeding database with observations and backfilling forecasts..."
	@$(PYTHON_BACKEND) scripts/seed_data.py --reset --forecasts 30

# --- Real Data Pipeline & ML ---

download-data:
	@echo "Downloading official CWC and CPCB telemetry datasets..."
	@$(PYTHON_ML) scripts/download_data.py

validate-data:
	@echo "Validating datasets and checking storage budget..."
	@$(PYTHON_ML) scripts/validate_data.py --fail-on-missing

preprocess:
	@echo "Cleaning telemetry and generating hydrological feature tables..."
	@$(PYTHON_ML) scripts/preprocess_data.py

train:
	@echo "Training models on real data and promoting candidate..."
	@$(PYTHON_ML) scripts/train.py --promote

evaluate:
	@echo "Evaluating holdout performance..."
	@$(PYTHON_ML) scripts/evaluate.py

predict:
	@echo "Running prediction for sample districts (Nashik, Jalgaon, Kolhapur)..."
	@$(PYTHON_ML) scripts/predict.py --districts MH-NAS,MH-JAL,MH-KOL

# --- Test Suites ---

test-backend:
	@echo "Running backend test suite..."
	@$(PYTEST_BACKEND) backend/tests/ -q

test-ml:
	@echo "Running ML and real-data pipeline test suite..."
	@$(PYTEST_ML) ml/tests/ -q

test-frontend:
	@echo "Running frontend unit & component tests..."
	@cd frontend && npm test -- --run

test: test-ml test-backend test-frontend
	@echo "All test suites passed successfully!"

build-frontend:
	@echo "Building Next.js production frontend..."
	@cd frontend && npm run build

clean:
	@echo "Cleaning cache files..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".next" -exec rm -rf {} + 2>/dev/null || true
	@echo "Clean completed."
