#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================"
echo "  Energy Meter Protocol Test (COM33)"
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
if [ ! -f "venv/.deps_installed" ] || ! diff -q requirements.txt venv/.deps_installed >/dev/null 2>&1; then
    echo "Installing dependencies..."
    pip install -r requirements.txt -q -i https://pypi.tuna.tsinghua.edu.cn/simple
    cp requirements.txt venv/.deps_installed
else
    echo "Dependencies up to date."
fi
echo ""

echo "[3/3] Running unit tests..."
echo "============================================"
python3 -m pytest tests/ -v
echo ""
echo "============================================"
echo "  Running live meter test (COM33)..."
echo "============================================"
python3 test_meter_live.py --port COM33 --baudrate 9600
