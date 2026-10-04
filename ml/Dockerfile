# syntax=docker/dockerfile:1
# Reproducible training environment. Used for `docker compose run ml` and for
# executing the notebooks; it is not part of the long-running service stack.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /workspace

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential git \
    && rm -rf /var/lib/apt/lists/*

COPY ml/requirements.txt ./ml/requirements.txt
RUN pip install --no-cache-dir -r ml/requirements.txt

COPY ml/pyproject.toml ./ml/pyproject.toml
COPY ml/src ./ml/src
RUN pip install --no-cache-dir -e ./ml

COPY ml/configs ./ml/configs
COPY scripts ./scripts
COPY data ./data

# The application package is needed only by scripts that record training runs.
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/app ./backend/app
ENV PYTHONPATH=/workspace/backend:/workspace/ml/src

RUN useradd --create-home --uid 10002 mlrunner && chown -R mlrunner:mlrunner /workspace
USER mlrunner

CMD ["python", "scripts/run_training.py", "--help"]
