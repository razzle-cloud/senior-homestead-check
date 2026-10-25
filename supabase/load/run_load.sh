#!/bin/zsh
# Loads the exported CSVs into the decatur-exemptions Supabase project.
# Your connection string is read with hidden input and never written to disk.
set -e
cd "$(dirname "$0")"
if ! command -v psql >/dev/null 2>&1; then
  for p in /Applications/Postgres.app/Contents/Versions/latest/bin /opt/homebrew/opt/libpq/bin /usr/local/opt/libpq/bin; do [ -x "$p/psql" ] && export PATH="$p:$PATH"; done
fi
if ! command -v psql >/dev/null 2>&1; then
  echo "psql not found. Install Postgres.app from https://postgresapp.com (drag it into Applications), then run this script again."
  exit 1
fi
echo "Paste your Supabase connection string (Session pooler URI, with your password filled in), then press Enter:"
read -rs DBURL
echo
export PGSSLMODE=require
psql "$DBURL" -v ON_ERROR_STOP=1 -f load.sql
