#!/bin/sh
set -e

# ==============================================================================
# MADAM HY SMART SHOP — CONTAINER ENTRYPOINT SCRIPT
# ==============================================================================

echo "==> [Smart Shop] Starting container entrypoint..."

# Wait for MySQL database connection if DB_HOST is defined
if [ -n "${DB_HOST:-}" ]; then
    DB_PORT="${DB_PORT:-3306}"
    echo "==> [Smart Shop] Waiting for database at ${DB_HOST}:${DB_PORT}..."
    
    RETRIES=30
    until nc -z "${DB_HOST}" "${DB_PORT}" || [ $RETRIES -eq 0 ]; do
        echo "==> [Smart Shop] Database unavailable. Waiting 2 seconds... ($RETRIES retries remaining)"
        sleep 2
        RETRIES=$((RETRIES - 1))
    done

    if [ $RETRIES -eq 0 ]; then
        echo "==> [Smart Shop ERROR] Failed to connect to database at ${DB_HOST}:${DB_PORT}."
        exit 1
    fi
    echo "==> [Smart Shop] Database connection established successfully."
fi

# Run database migrations automatically in production container
echo "==> [Smart Shop] Applying database migrations..."
python manage.py migrate --noinput

# Collect static assets into STATIC_ROOT
echo "==> [Smart Shop] Collecting static files..."
python manage.py collectstatic --noinput

echo "==> [Smart Shop] Bootstrap completed successfully. Launching application process..."

# Execute container command (e.g. gunicorn)
exec "$@"
