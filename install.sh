#!/bin/bash
set -euo pipefail

# Absolute paths to packages
ROOT_DIR=$(pwd)
ASPYX_PATH="$ROOT_DIR/packages/aspyx"
ASPYX_SERVICE_PATH="$ROOT_DIR/packages/aspyx_service"

echo "Installing aspyx..."
pip install -e "$ASPYX_PATH"

echo "Installing aspyx_service..."
pip install -e "$ASPYX_SERVICE_PATH"

echo "All done!"