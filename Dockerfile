FROM python:3.14-slim

LABEL org.opencontainers.image.source="https://github.com/Hochfrequenz/sapgui.mcp"
LABEL org.opencontainers.image.description="MCP server for SAP Web GUI browser automation"
LABEL org.opencontainers.image.licenses="MIT"
LABEL authors="Hochfrequenz Unternehmensberatung GmbH"
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN adduser --disabled-password --gecos "" appuser
WORKDIR /app

COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser requirements.txt .
# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt
# If you try to run `pip install .` with a pyproject.toml, you'll have problems with the build, because the git tag version is undefined.
# LookupError: Error getting the version from source `vcs`: setuptools-scm was unable to detect version for /app
# That's why we cannot use the CLI shortcut in the entrypoint below.

# Install Playwright and Chromium browser with dependencies
RUN pip install playwright && playwright install chromium --with-deps

COPY --chown=appuser:appuser src/ ./src/
COPY pyproject.toml .
COPY README.md .

# Install the package (must be done as root before switching user)
# Set fake version only if not provided - Docker build has no git metadata for hatch-vcs
RUN SETUPTOOLS_SCM_PRETEND_VERSION=${SETUPTOOLS_SCM_PRETEND_VERSION:-0.0.0.dev0+docker} \
    pip install --no-cache-dir .

USER appuser

# Default to connect mode since Docker containers don't have displays.
# Users should run a browser with --remote-debugging-port=9222 on the host.
ENV BROWSER_MODE=connect
ENV BROWSER_TYPE=chromium
ENV CDP_URL=http://host.docker.internal:9222

# MCP servers communicate via stdin/stdout, so just run the server directly
ENTRYPOINT ["run-sapgui-mcp-server"]