#!/bin/bash
set -e

echo "### build aspyx"
cd packages/aspyx
hatch build

echo "### build aspyx_service"
ls ../aspyx_service
cd ../aspyx_service
hatch build