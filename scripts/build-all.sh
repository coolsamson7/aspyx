#!/bin/bash
set -e

echo "### build aspyx"
cd packages/aspyx
hatch build

echo "### build aspyx_service"
cd ../aspyx_service
hatch build

echo "### build aspyx_event"
cd ../aspyx_event
hatch build