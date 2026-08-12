FROM python:3.14-slim

# Pin the uv version (matches ebd_toolchain); the base image ships pip but no uv.
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /uvx /bin/

LABEL org.opencontainers.image.source="https://github.com/Hochfrequenz/sapgui.mcp"
LABEL org.opencontainers.image.description="MCP server for SAP Web GUI browser automation"
LABEL org.opencontainers.image.licenses="MIT"
LABEL authors="Hochfrequenz Unternehmensberatung GmbH"
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Use the image's interpreter instead of downloading a managed CPython.
    UV_PYTHON_DOWNLOADS=never \
    # Download the browser to a shared location readable by appuser (the install
    # runs as root, the entrypoint runs as appuser).
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

RUN adduser --disabled-password --gecos "" appuser
WORKDIR /app

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first (cached layer). The project has a dynamic version
# (hatch-vcs) so a SETUPTOOLS_SCM_PRETEND_VERSION is supplied for any build step;
# --locked only checks that the resolved dependencies match uv.lock, which is
# unaffected by the pretend version because uv.lock records no version for the
# dynamic root package.
COPY pyproject.toml uv.lock README.md ./
RUN SETUPTOOLS_SCM_PRETEND_VERSION=${SETUPTOOLS_SCM_PRETEND_VERSION:-0.0.0.dev0+docker} \
    uv sync --locked --no-dev --no-install-project --no-editable

# Install Chromium browser (with OS deps) from the synced venv, as root.
RUN /app/.venv/bin/playwright install chromium --with-deps

# Install the project itself. --no-editable installs a real copy (as pip did),
# which the run-sapgui-mcp-server console script needs.
COPY --chown=appuser:appuser src/ ./src/
RUN SETUPTOOLS_SCM_PRETEND_VERSION=${SETUPTOOLS_SCM_PRETEND_VERSION:-0.0.0.dev0+docker} \
    uv sync --locked --no-dev --no-editable

ENV PATH="/app/.venv/bin:$PATH"

USER appuser

# Default to connect mode since Docker containers don't have displays.
# Users should run a browser with --remote-debugging-port=9222 on the host.
ENV BROWSER_MODE=connect
ENV BROWSER_TYPE=chromium
ENV CDP_URL=http://host.docker.internal:9222

# MCP servers communicate via stdin/stdout, so just run the server directly
ENTRYPOINT ["run-sapgui-mcp-server"]
