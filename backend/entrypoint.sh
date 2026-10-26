#!/bin/sh
set -e

echo "=== Running Database Migrations ==="
alembic upgrade head

echo "=== Seeding Database (if empty) ==="
python scripts/seed_demo.py

echo "=== Starting PayTrace API Server ==="
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
