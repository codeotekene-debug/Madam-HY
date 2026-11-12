#!/usr/bin/env bash
# ==============================================================================
# MADAM HY SMART SHOP — AUTOMATED ZERO-DOWNTIME DEPLOYMENT SCRIPT
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BRANCH="${1:-main}"

echo "=============================================================================="
echo "  MADAM HY SMART SHOP — PRODUCTION DEPLOYMENT START"
echo "  Target Branch: ${BRANCH}"
echo "  Working Directory: ${APP_DIR}"
echo "=============================================================================="

cd "${APP_DIR}"

# ------------------------------------------------------------------------------
# 1. PRE-FLIGHT CHECKS
# ------------------------------------------------------------------------------
echo "==> [Phase 1/6] Running pre-flight validations..."

if [ ! -d ".git" ]; then
    echo "==> [ERROR] Directory is not a git repository!"
    exit 1
fi

if [ ! -f ".env.production" ] && [ ! -f ".env" ]; then
    echo "==> [ERROR] Neither .env.production nor .env found!"
    exit 1
fi

# ------------------------------------------------------------------------------
# 2. AUTOMATED PRE-MIGRATION BACKUP
# ------------------------------------------------------------------------------
echo "==> [Phase 2/6] Executing pre-deployment database backup..."
if [ -x "${SCRIPT_DIR}/backup_db.sh" ]; then
    "${SCRIPT_DIR}/backup_db.sh"
else
    bash "${SCRIPT_DIR}/backup_db.sh"
fi

# ------------------------------------------------------------------------------
# 3. CODEBASE UPDATE
# ------------------------------------------------------------------------------
echo "==> [Phase 3/6] Fetching latest release from Git (${BRANCH})..."
git fetch origin "${BRANCH}"
git checkout "${BRANCH}"
git pull --ff-only origin "${BRANCH}"

# ------------------------------------------------------------------------------
# 4. PYTHON DEPENDENCIES & VIRTUAL ENVIRONMENT
# ------------------------------------------------------------------------------
echo "==> [Phase 4/6] Synchronizing Python virtual environment dependencies..."

VENV_PATH="${APP_DIR}/.venv"
if [ ! -d "${VENV_PATH}" ]; then
    echo "==> Creating virtual environment at ${VENV_PATH}..."
    python3 -m venv "${VENV_PATH}"
fi

# shellcheck disable=SC1091
source "${VENV_PATH}/bin/activate"

pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
pip install gunicorn cryptography

# ------------------------------------------------------------------------------
# 5. DATABASE MIGRATIONS & STATIC COLLECTION
# ------------------------------------------------------------------------------
echo "==> [Phase 5/6] Executing database migrations and collecting static assets..."

python manage.py check --deploy
python manage.py migrate --noinput
python manage.py collectstatic --noinput

# ------------------------------------------------------------------------------
# 6. GRACEFUL SERVICE RELOAD (ZERO-DOWNTIME)
# ------------------------------------------------------------------------------
echo "==> [Phase 6/6] Reloading application workers..."

if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet smart_shop.service; then
    echo "==> Reloading systemd service (smart_shop.service via SIGHUP)..."
    sudo systemctl reload smart_shop.service
elif [ -f "${APP_DIR}/deploy/docker/docker-compose.prod.yml" ] && command -v docker >/dev/null 2>&1 && docker compose -f "${APP_DIR}/deploy/docker/docker-compose.prod.yml" ps --services 2>/dev/null | grep -q "web"; then
    echo "==> Restarting Docker web service gracefully..."
    docker compose -f "${APP_DIR}/deploy/docker/docker-compose.prod.yml" restart web
else
    # Fallback to PID file or pkill SIGHUP if running standalone gunicorn
    if pgrep -f "gunicorn.*config.wsgi" >/dev/null 2>&1; then
        echo "==> Sending SIGHUP signal to Gunicorn master process..."
        pkill -HUP -f "gunicorn.*config.wsgi"
    else
        echo "==> [NOTICE] Gunicorn process not running. Service ready for cold start."
    fi
fi

echo "=============================================================================="
echo "  MADAM HY SMART SHOP — DEPLOYMENT COMPLETED SUCCESSFULLY"
echo "  Timestamp: $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "=============================================================================="
