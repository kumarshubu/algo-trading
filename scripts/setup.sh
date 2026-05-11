#!/usr/bin/env bash
# Project setup script - run once after cloning

set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "Setting up Algo Trading Platform (Paper Only)"
echo "============================================="

# --- Backend ---
echo ""
echo "[1/4] Setting up Python virtual environment..."
cd "$REPO_ROOT/backend"
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "     Done."

# --- .env ---
echo ""
echo "[2/4] Creating .env from .env.example..."
cd "$REPO_ROOT"
if [ ! -f .env ]; then
  cp .env.example .env
  echo "     Created .env - review and update values if needed."
else
  echo "     .env already exists - skipping."
fi

# --- Alembic ---
echo ""
echo "[3/4] Running Alembic migrations..."
cd "$REPO_ROOT/backend"
source .venv/bin/activate
alembic upgrade head
echo "     Done."

# --- Frontend ---
echo ""
echo "[4/5] Installing frontend Node.js dependencies..."
cd "$REPO_ROOT/frontend"
npm install --legacy-peer-deps
echo "     Done."

# --- Root (concurrently) ---
echo ""
echo "[5/5] Installing root dev dependencies (concurrently)..."
cd "$REPO_ROOT"
npm install
echo "     Done."

echo ""
echo "============================================="
echo "Setup complete!"
echo ""
echo "  npm run dev       start backend + frontend together"
echo "  npm run test      run backend tests"
echo "  npm run build     build frontend for production"
echo ""
echo "Backend API docs: http://127.0.0.1:8000/docs"
echo "Frontend:         http://localhost:3000"
echo ""
echo "REMINDER: This platform is for PAPER TRADING ONLY."
echo "          No real trades will be placed."
