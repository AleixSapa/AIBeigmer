#!/bin/sh
set -e

# Start FastAPI internally; Nginx remains the public process on port 80.
python3 -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 &
exec nginx -g 'daemon off;'
