#!/usr/bin/env bash
# One-time local setup: virtualenvs, dependencies, database, dataset, model.
#
#   ./scripts/setup.sh              # full setup
#   ./scripts/setup.sh --skip-train # stop after seeding, reuse an existing artifact
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

SKIP_TRAIN=0
SKIP_FRONTEND=0
for arg in "$@"; do
  case "$arg" in
    --skip-train) SKIP_TRAIN=1 ;;
    --skip-frontend) SKIP_FRONTEND=1 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

info() { printf '\n\033[1;34m==>\033[0m %s\n' "$1"; }
warn() { printf '\033[1;33mwarning:\033[0m %s\n' "$1"; }
fail() { printf '\033[1;31merror:\033[0m %s\n' "$1" >&2; exit 1; }

command -v python3 >/dev/null || fail "python3 is required"
command -v node >/dev/null || fail "node is required"

# --- environment -----------------------------------------------------------
info "Preparing environment file"
if [ ! -f .env ]; then
  cp .env.example .env
  warn "created .env from .env.example; update POSTGRES_* to match your database"
else
  echo ".env already exists, leaving it untouched"
fi

# --- Python ----------------------------------------------------------------
info "Creating backend virtualenv"
python3 -m venv backend/.venv
backend/.venv/bin/pip install --quiet --upgrade pip
backend/.venv/bin/pip install --quiet -r backend/requirements.txt

info "Creating ML virtualenv"
python3 -m venv ml/.venv
ml/.venv/bin/pip install --quiet --upgrade pip
ml/.venv/bin/pip install --quiet -r ml/requirements.txt
ml/.venv/bin/pip install --quiet -e ./ml

# --- frontend --------------------------------------------------------------
if [ "$SKIP_FRONTEND" -eq 0 ]; then
  if command -v npm >/dev/null; then
    info "Installing frontend dependencies"
    (cd frontend && npm install --no-audit --no-fund)
  else
    warn "npm not found; skipping frontend install"
  fi
fi

# --- database --------------------------------------------------------------
info "Waiting for PostgreSQL"
# shellcheck source=/dev/null
source <(grep -E '^(POSTGRES_HOST|POSTGRES_PORT)=' .env | sed 's/^/export /' || true)
DB_HOST="${POSTGRES_HOST:-localhost}"
DB_PORT="${POSTGRES_PORT:-5432}"

ready=0
for _ in $(seq 1 30); do
  if pg_isready -h "$DB_HOST" -p "$DB_PORT" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done

if [ "$ready" -eq 1 ]; then
  info "Running database migrations"
  # Alembic resolves the URL from the repository root .env, so it can be run
  # from either directory.
  backend/.venv/bin/alembic -c database/alembic.ini upgrade head
else
  warn "PostgreSQL is not reachable on $DB_HOST:$DB_PORT."
  warn "Start it (docker compose up -d db, or your own instance) and re-run this script."
fi

# --- dataset ---------------------------------------------------------------
if [ ! -f data/processed/observations.csv ]; then
  info "Generating the synthetic demo dataset"
  ml/.venv/bin/python scripts/generate_demo_dataset.py
else
  echo "dataset already present, skipping generation"
fi

# --- model -----------------------------------------------------------------
if [ "$SKIP_TRAIN" -eq 0 ]; then
  if ls ml/artifacts/v*/metadata.json >/dev/null 2>&1; then
    echo "model artifacts already present; skipping training (pass --skip-train to keep this)"
  else
    info "Training the first model (this takes a minute)"
    ml/.venv/bin/python scripts/run_training.py
  fi
fi

# --- seed ------------------------------------------------------------------
if [ "$ready" -eq 1 ] && [ "$SKIP_TRAIN" -eq 0 ]; then
  info "Seeding the database"
  backend/.venv/bin/python scripts/seed_data.py
fi

cat <<'SUMMARY'

Setup complete.

  Terminal 1  cd backend  && .venv/bin/uvicorn app.main:app --reload
  Terminal 2  cd frontend && npm run dev

  API docs    http://localhost:8000/docs
  Dashboard   http://localhost:3000

Run `docker compose --profile app up -d` to use containers instead.
SUMMARY
