FROM docker.repo.severstal.severstalgroup.com/devops-public/corp-images/python:3.13-debian AS builder

USER root

RUN update-ca-certificates && \
    (getent group user || groupadd --gid 10000 user) && \
    (getent passwd user || useradd --uid 10000 --gid 10000 --shell /bin/bash --create-home user) && \
    mkdir -p /app && \
    chown user:user /app

RUN rm -f /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libssl-dev

RUN mkdir -p /root/.pip && \
    printf '%s\n' \
      '[global]' \
      'index-url = https://repo.severstal.severstalgroup.com/artifactory/api/pypi/pypi/simple' \
      'trusted-host = repo.severstal.severstalgroup.com' \
      > /root/.pip/pip.conf

ENV PIP_DEFAULT_TIMEOUT=120 \
    POETRY_HTTP_TIMEOUT=120

ARG POETRY_VERSION=2.2.1

RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir --retries 15 --timeout 120 "poetry==${POETRY_VERSION}" && \
    poetry config virtualenvs.create false && \
    apt-get purge -y build-essential libffi-dev libssl-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml poetry.lock README.md ./

RUN poetry install --no-root --no-interaction --without dev && \
    pip uninstall -y poetry


# Runtime stage
FROM docker.repo.severstal.severstalgroup.com/devops-public/corp-images/python:3.13-debian AS runtime

USER root

RUN update-ca-certificates && \
    (getent group user || groupadd --gid 10000 user) && \
    (getent passwd user || useradd --uid 10000 --gid 10000 --shell /bin/bash --create-home user) && \
    mkdir -p /app && \
    chown user:user /app

RUN rm -f /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    fonts-dejavu-core \
    libfreetype6 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin/ /usr/local/bin/
RUN rm -f /usr/local/bin/poetry*

COPY app/ ./app/
COPY config/ ./config/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# OpenTelemetry: set OTEL_* via Helm/compose (e.g. OTLP to Jaeger). Traces off if unset.
ENV OTEL_METRICS_EXPORTER=none \
    OTEL_LOGS_EXPORTER=none

USER user

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Zero-code tracing: opentelemetry-instrument wraps the server and exports via OTLP.
CMD ["opentelemetry-instrument", "gunicorn", "app.main:app", "-c", "config/gunicorn_conf.py"]
