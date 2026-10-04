# syntax=docker/dockerfile:1
# Backend image. Trains nothing: the artifact is produced separately and mounted
# or copied in, which keeps the serving image free of the training stack.

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libpq5 \
    && rm -rf /var/lib/apt/lists/*

# The inference feature builder is shared with the training package, so the
# build context is the repository root and `rainml` is installed from source.
# Build with: docker build -f backend/Dockerfile .
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY ml/pyproject.toml ./ml/pyproject.toml
COPY ml/src ./ml/src
RUN pip install --no-cache-dir ./ml

COPY backend/app ./app
COPY backend/pyproject.toml ./pyproject.toml
COPY database ./database
# The seeding and job scripts are needed in the image so a containerised
# deployment can be initialised without a host checkout.
COPY scripts ./scripts
# Seed data and trained artifacts live in the repository, not in the image.
COPY data ./data
COPY ml/artifacts ./ml/artifacts

# The application reads artifacts from this path; a volume mount overrides it.
ENV MODEL_ARTIFACT_PATH=/app/ml/artifacts
RUN mkdir -p /app/ml/artifacts

# The package lives at /app/app, so /app must be importable from any cwd.
ENV PYTHONPATH=/app
WORKDIR /app

RUN useradd --create-home --uid 10001 corrector && chown -R corrector:corrector /app
USER corrector

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
