#!/bin/bash
set -euo pipefail

# Absolute paths to packages
ROOT_DIR=$(pwd)
ASPYX_PATH="$ROOT_DIR/packages/aspyx"
ASPYX_SERVICE_PATH="$ROOT_DIR/packages/aspyx_service"
ASPYX_EVENT_PATH="$ROOT_DIR/packages/aspyx_event"
ASPYX_JOB_PATH="$ROOT_DIR/packages/aspyx_job"
ASPYX_PERSISTENCE_PATH="$ROOT_DIR/packages/aspyx_persistence"
ASPYX_SECURITY_PATH="$ROOT_DIR/packages/aspyx_security"

echo "Installing aspyx..."
pip install -e "$ASPYX_PATH"

echo "Installing aspyx_service..."
pip install -e "$ASPYX_SERVICE_PATH"

echo "Installing aspyx_event..."
pip install -e "$ASPYX_EVENT_PATH"

echo "Installing aspyx_job..."
pip install -e "$ASSAIA_JOB_PATH"

echo "Installing aspyx_security..."
pip install -e "$ASSAIA_SECURITY_PATH"

echo "Installing aspyx_persistence..."
pip install -e "$ASSAIA_PERSISTENCE_PATH"

echo "All done!"