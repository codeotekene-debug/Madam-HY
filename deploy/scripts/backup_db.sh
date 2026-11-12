#!/usr/bin/env bash
# ==============================================================================
# MADAM HY SMART SHOP — AUTOMATED DATABASE BACKUP SCRIPT
# ==============================================================================
set -euo pipefail

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Configuration & Defaults
BACKUP_DIR="${BACKUP_DIR:-/var/backups/smart_shop/db}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

# Source production environment variables if present
if [ -f "${APP_DIR}/.env.production" ]; then
    set -a
    # shellcheck disable=SC1091
    source "${APP_DIR}/.env.production"
    set +a
elif [ -f "${APP_DIR}/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "${APP_DIR}/.env"
    set +a
fi

DB_NAME="${DB_NAME:-madam_hy}"
DB_USER="${DB_USER:-madam_user}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-3306}"
DB_PASSWORD="${DB_PASSWORD:-}"

echo "==> [Smart Shop Backup] Starting MySQL backup for database: '${DB_NAME}'..."

# Ensure backup directory exists
mkdir -p "${BACKUP_DIR}"

BACKUP_FILE="${BACKUP_DIR}/${DB_NAME}_backup_${TIMESTAMP}.sql.gz"

# Execute mysqldump with atomic snapshot options
if [ -n "${DB_PASSWORD}" ]; then
    MYSQL_PWD="${DB_PASSWORD}" mysqldump \
        --host="${DB_HOST}" \
        --port="${DB_PORT}" \
        --user="${DB_USER}" \
        --single-transaction \
        --quick \
        --routines \
        --triggers \
        --default-character-set=utf8mb4 \
        "${DB_NAME}" | gzip -9 > "${BACKUP_FILE}"
else
    mysqldump \
        --host="${DB_HOST}" \
        --port="${DB_PORT}" \
        --user="${DB_USER}" \
        --single-transaction \
        --quick \
        --routines \
        --triggers \
        --default-character-set=utf8mb4 \
        "${DB_NAME}" | gzip -9 > "${BACKUP_FILE}"
fi

# Verify gzip archive integrity
if gzip -t "${BACKUP_FILE}"; then
    FILE_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
    echo "==> [Smart Shop Backup SUCCESS] Backup created: ${BACKUP_FILE} (${FILE_SIZE})"
else
    echo "==> [Smart Shop Backup ERROR] Backup verification failed for ${BACKUP_FILE}!"
    exit 1
fi

# Prune old backups older than RETENTION_DAYS
echo "==> [Smart Shop Backup] Pruning backups older than ${RETENTION_DAYS} days..."
find "${BACKUP_DIR}" -type f -name "${DB_NAME}_backup_*.sql.gz" -mtime +"${RETENTION_DAYS}" -print -delete || true

echo "==> [Smart Shop Backup] Backup and retention cycle completed."
