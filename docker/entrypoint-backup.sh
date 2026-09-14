#!/bin/sh
# Backup sidecar: run one backup now, then hand over to cron for the nightly job.
#
# The immediate backup matters — it means a freshly deployed instance is never
# sitting there with no backup at all, waiting for 03:30 to come around.
set -e

BACKUP_TIME="${BACKUP_TIME:-03:30}"
HOUR="${BACKUP_TIME%%:*}"
MINUTE="${BACKUP_TIME##*:}"
# Strip a leading zero so cron doesn't read "03" as octal in some shells.
HOUR="$(expr "$HOUR" + 0)"
MINUTE="$(expr "$MINUTE" + 0)"

echo "[backup] data dir: ${DATA_DIR:-/data}"
echo "[backup] schedule: daily at ${BACKUP_TIME} (cron: ${MINUTE} ${HOUR} * * *)"
echo "[backup] retention: ${BACKUP_RETENTION_DAYS:-30} days"

# Run one now so the instance always has a recent backup.
python -m scripts.backup || echo "[backup] initial backup skipped (no progress DB yet)"

# cron runs with a near-empty environment, so bake the settings the job needs
# into the crontab rather than relying on inheritance.
cat > /etc/cron.d/mandarin-backup <<CRON
SHELL=/bin/sh
PATH=/usr/local/bin:/usr/bin:/bin
DATA_DIR=${DATA_DIR:-/data}
BACKUP_RETENTION_DAYS=${BACKUP_RETENTION_DAYS:-30}
${MINUTE} ${HOUR} * * * root cd /app/backend && python -m scripts.backup >> /data/backups/backup.log 2>&1
CRON
chmod 0644 /etc/cron.d/mandarin-backup

mkdir -p /data/backups
touch /data/backups/backup.log

# -f keeps cron in the foreground so the container stays alive and Docker can
# restart it if cron ever dies.
exec cron -f -L 2
