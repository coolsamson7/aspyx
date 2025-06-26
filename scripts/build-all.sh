#!/bin/bash
set -e
cd packages/aspyx && hatch build
cd ../aspyx_service && hatch build