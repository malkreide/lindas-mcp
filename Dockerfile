# syntax=docker/dockerfile:1.7
# Multi-stage build: install deps with pip into a venv, then ship a slim runtime.
FROM python:3.13-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/

RUN python -m venv /app/.venv \
    && /app/.venv/bin/pip install --no-cache-dir .

# ---------------------------------------------------------------------------

FROM python:3.13-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    LINDAS_MCP_TRANSPORT=streamable-http \
    HOST=0.0.0.0 \
    PORT=8000

RUN groupadd --system mcp \
    && useradd --system --gid mcp --home-dir /app --shell /usr/sbin/nologin mcp

WORKDIR /app
COPY --from=builder --chown=mcp:mcp /app/.venv /app/.venv

USER mcp
EXPOSE 8000

# SCALE-004: let orchestrators/load balancers detect an unhealthy container.
# Either HTTP transport opens PORT; a successful TCP connect means the server is
# up. It does not distinguish them, nor a stdio fall-through — that one opens no
# port at all and shows up here as an unhealthy container.
# Uses stdlib only (no curl in the slim image).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,socket; socket.create_connection(('127.0.0.1', int(os.getenv('PORT','8000'))), 3).close()" || exit 1

# Read-only, no-auth public-data server — no secrets required at runtime.
#
# The console entry point, not `python -m lindas_mcp.server`: `__init__.py`
# imports `.server`, so `-m` loaded the module twice — once as
# `lindas_mcp.server` during the package import, then again as `__main__`. That
# is the `RuntimeWarning: 'lindas_mcp.server' found in sys.modules ...` every
# container start logged, and it left two distinct `MCPServer` instances in the
# process (measured: the two `mcp` objects are not identical). The served one
# was the `__main__` copy, so nothing broke — the first was dead weight with its
# own module-level state. `lindas-mcp` resolves via /app/.venv/bin on PATH and
# imports `lindas_mcp.server:main` exactly once.
CMD ["lindas-mcp"]
