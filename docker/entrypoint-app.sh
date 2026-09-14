#!/bin/sh
# App server: migrate/init the databases, then serve API + SPA.
set -e

echo "[app] data dir: ${DATA_DIR:-/data}"

# Split a pre-existing single-file DB before the server touches it. init_db()
# does this too, but running it here means a migration failure stops the
# container loudly instead of part-way through startup.
python -m scripts.migrate_split_db

exec python -m app
