#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================"
echo "  MQTT WebSocket Serial Transparent Server"
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

echo "Installing dependencies..."
pip install -r requirements.txt -q
echo ""

# Start server
echo "[3/3] Starting server..."
echo "============================================"
python3 server.py
