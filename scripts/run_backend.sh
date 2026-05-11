#!/usr/bin/env bash
# Start the FastAPI backend server

set -e
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT/backend"

if [ ! -d ".venv" ]; then
  echo "Virtual environment not found. Run scripts/setup.sh first."
  exit 1
fi

source .venv/bin/activate

echo "Starting backend server..."
echo "API docs: http://127.0.0.1:8000/docs"
echo "PAPER TRADING ONLY - NO REAL EXECUTION"
echo ""

uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
