#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================"
echo "  Unified Serial Server (MQTT WS + API)"
echo "============================================"
echo ""

# Pull latest code
echo "[1/3] Updating code from git..."
git pull || echo "WARNING: Git pull failed, continuing with current code..."
echo ""

# Setup Python venv
echo "[2/3] Setting up Python environment..."
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi
source venv/bin/activate

# Only install if first run or requirements.txt changed
if [ ! -f "venv/.deps_installed" ] || ! diff -q requirements.txt venv/.deps_installed >/dev/null 2>&1; then
    echo "Installing dependencies..."
    pip install -r requirements.txt -q -i https://pypi.tuna.tsinghua.edu.cn/simple
    cp requirements.txt venv/.deps_installed
else
    echo "Dependencies up to date."
fi
echo ""

# Start unified server (MQTT WS bridge + Meter API)
echo "[3/3] Starting unified server..."
echo "  MQTT WS bridge: serial/comXX/up, serial/comXX/down"
echo "  Meter API: http://localhost:8000/docs"
echo "============================================"
python3 server.py
