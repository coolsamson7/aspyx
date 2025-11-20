#!/bin/bash
set -euo pipefail

# Absolute paths to packages
ROOT_DIR=$(pwd)
ASPYX_PATH="$ROOT_DIR/packages/aspyx"
ASPYX_SERVICE_PATH="$ROOT_DIR/packages/aspyx_service"
ASPYX_EVENT_PATH="$ROOT_DIR/packages/aspyx_event"
ASPYX_JOB_PATH="$ROOT_DIR/packages/aspyx_job"
ASSAIA_PATH="$ROOT_DIR/packages/assaia"

echo "Installing aspyx..."
pip install -e "$ASPYX_PATH"

echo "Installing aspyx_service..."
pip install -e "$ASPYX_SERVICE_PATH"

echo "Installing aspyx_event..."
pip install -e "$ASPYX_EVENT_PATH"

echo "Installing aspyx_job..."
pip install -e "$ASSAIA_JOB_PATH"

echo "All done!"