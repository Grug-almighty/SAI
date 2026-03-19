#!/bin/bash
echo "Installing dependencies..."
pip3 install -r requirements.txt --break-system-packages 2>/dev/null || pip3 install -r requirements.txt
echo ""
echo "Starting SAI..."
python3 app.py
