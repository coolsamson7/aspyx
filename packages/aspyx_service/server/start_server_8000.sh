#!/bin/bash
export FAST_API_PORT=8000
uvicorn main:app --host 0.0.0.0 --port $FAST_API_PORT --workers 1 --log-level warning