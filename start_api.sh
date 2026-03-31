#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================"
echo "  Energy Meter API Service (COM33)"
echo "============================================"
echo ""

echo "[1/3] Updating code from git..."
git pull || echo "WARNING: Git pull failed, continuing with current code..."
echo ""

echo "[2/3] Setting up Python environment..."
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt -q
echo ""

echo "[3/3] Starting Meter API on http://0.0.0.0:8000 ..."
echo "  API docs: http://localhost:8000/docs"
echo "============================================"
python3 meter_api.py
