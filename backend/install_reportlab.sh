#!/bin/bash
# Uvicorn'un kullandığı Python'u bul ve reportlab kur
echo "=== Python versions ==="
which python3
python3 --version
which uvicorn
uvicorn --version 2>/dev/null || echo "uvicorn not in PATH"

echo ""
echo "=== Trying to install reportlab ==="
# Try all common python paths
for py in python3 python3.11 python3.12 python3.13 python3.14 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    if command -v $py &>/dev/null; then
        echo "Found: $($py --version)"
        $py -m pip install reportlab --quiet && echo "✅ Installed via $py" || echo "❌ Failed via $py"
    fi
done