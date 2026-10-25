#!/bin/zsh
# Runs one of the v2 pull scripts against Supabase.
#   zsh run_v2.sh coverage.py
#   zsh run_v2.sh pull_county.py --plan
# First run creates a private Python environment (.venv) and installs the libraries.
# Your connection string is read with hidden input and only kept for this one command.
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "Setting up the Python environment (one time)..."
  python3 -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt
fi
if [ -z "$1" ]; then
  echo "usage: zsh run_v2.sh <script.py> [options]   e.g.  zsh run_v2.sh coverage.py"
  exit 1
fi
if [ -z "$DATABASE_URL" ]; then
  echo "Paste your Supabase connection string (Session pooler URI, with your password), then press Enter:"
  read -rs DATABASE_URL
  echo
  export DATABASE_URL
fi
# keep the Mac awake while a long pull runs
exec caffeinate -i .venv/bin/python "$@"
