#!/usr/bin/env bash
# Start the Next.js frontend dev server

set -e
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT/frontend"

if [ ! -d "node_modules" ]; then
  echo "node_modules not found. Run scripts/setup.sh first."
  exit 1
fi

echo "Starting frontend..."
echo "URL: http://localhost:3000"
echo ""

npm run dev
