#!/bin/bash
set -e

# [1] Load exported environment variables
if [ ! -f misp-docker/sync_vars.sh ]; then
  echo "[!] sync_vars.sh file not found. Run INSTALL.sh first."
  exit 1
fi

source ./misp-docker/sync_vars.sh

# Activate the Python virtual environment
source ./env/bin/activate

# --- Run the Python unit test ---
python3 -m unittest discover -s tests -p "test_sync_*.py" -v

# --- Deactivate the virtual environment if needed ---
deactivate
