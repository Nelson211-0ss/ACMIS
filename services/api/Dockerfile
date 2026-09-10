# The API image.
#
# Two stages so the wheel-building toolchain never reaches production. The
# runtime layer carries Pango, Cairo and their dependencies because WeasyPrint
# links them at import time — transcripts and certificates are rendered to PDF
# by the reporting module, and a missing shared library there fails at the
# moment a registrar presses "issue", which is the worst possible time to find
# out.
FROM python:3.13-slim AS build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
# Dependencies resolve from the manifest alone, so this layer is cached across
# every change to the application itself.
COPY pyproject.toml ./
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip setuptools wheel \
    && /opt/venv/bin/pip install .


FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        libffi8 \
        fonts-dejavu-core \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /opt/venv /opt/venv

WORKDIR /app
COPY acmis ./acmis
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY pyproject.toml ./pyproject.toml

# Unprivileged, and the application directory stays read-only to it: nothing
# the API does at runtime writes to its own source tree, so anything that tries
# is a bug or an intrusion and should fail rather than succeed quietly.
RUN useradd --system --uid 10001 --create-home --shell /usr/sbin/nologin acmis \
    && chown -R root:root /app
USER acmis

EXPOSE 8000

# `/health/live` answers without touching Postgres or Redis, which is what a
# liveness probe wants — a database outage should not make Docker restart a
# process that is working correctly and reporting the outage.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health/live || exit 1

# One worker per container. Scaling is horizontal — `docker compose up
# --scale api=N` behind the proxy — because the ABAC policy bundle and the
# tenant engine cache are per-process, and four workers in one container means
# four copies of both with no way to invalidate them together.
CMD ["uvicorn", "acmis.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
