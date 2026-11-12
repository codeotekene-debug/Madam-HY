# ==============================================================================
# MADAM HY SMART SHOP — MULTI-STAGE PRODUCTION DOCKERFILE
# ==============================================================================

# ------------------------------------------------------------------------------
# STAGE 1: Build & Dependencies
# ------------------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system compilation dependencies for mysqlclient and pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    libssl-dev \
    zlib1g-dev \
    libjpeg-dev \
    && rm -rf /var/lib/apt/lists/*

# Create isolated Python virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install production Python packages
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt && \
    pip install gunicorn cryptography

# ------------------------------------------------------------------------------
# STAGE 2: Production Runtime
# ------------------------------------------------------------------------------
FROM python:3.12-slim AS runner

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Install runtime libraries only (no compiler tools in production image)
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-mysql-client \
    curl \
    netcat-openbsd \
    libjpeg62-turbo \
    zlib1g \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv

# Create unprivileged system user and group for security
RUN groupadd --system --gid 1001 smartshop && \
    useradd --system --uid 1001 --gid 1001 --no-create-home smartshop

# Prepare application runtime directories with appropriate permissions
RUN mkdir -p /app/staticfiles /app/media /app/logs && \
    chown -R smartshop:smartshop /app

# Copy application source code into container
COPY --chown=smartshop:smartshop . /app

# Ensure shell scripts have executable permissions
RUN chmod +x /app/deploy/docker/entrypoint.sh

# Switch to unprivileged runtime user
USER smartshop

# Expose Gunicorn application server port
EXPOSE 8000

# Container healthcheck testing root endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/accounts/login/ || exit 1

# Entrypoint manages database readiness, migrations, and collectstatic
ENTRYPOINT ["/app/deploy/docker/entrypoint.sh"]

# Default command launches Gunicorn WSGI server with production worker configuration
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "--threads", "2", "--worker-class", "gthread", "--access-logfile", "-", "--error-logfile", "-", "config.wsgi:application"]
