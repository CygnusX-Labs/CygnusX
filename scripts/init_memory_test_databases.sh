#!/bin/sh
set -eu

# POSTGRES_DB is created by the image.  This init hook runs only on a fresh
# disposable volume and creates the two additional Stage 0 databases.
for database in cygnusx_accept cygnusx_maint; do
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -c "CREATE DATABASE \"$database\";"
done
