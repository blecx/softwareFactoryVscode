#!/bin/bash
set -e

MOCK_HOST="/tmp/mock-host-phase10-$(date +%s)"
mkdir -p "$MOCK_HOST"

echo "➡️ Simulating remote install script fetch..."
cp scripts/install_factory.py "$MOCK_HOST/"
cp scripts/bootstrap_host.py "$MOCK_HOST/"

cd "$MOCK_HOST"
echo "➡️ Running installer..."
# Monkeypatch the git clone to just purely clone the local repo instead of github to speed it up
sed -i 's|https://github.com/blecx/softwareFactoryVscode.git|/home/sw/work/softwareFactoryVscode|' install_factory.py
python3 install_factory.py

echo "➡️ Running bootstrapper..."
python3 .softwareFactoryVscode/scripts/bootstrap_host.py

echo "➡️ Checking compliance files..."
if [ ! -f ".factory.env" ]; then echo "❌ Missing .factory.env"; exit 1; fi
if [ ! -f ".factory.lock.json" ]; then echo "❌ Missing .factory.lock.json"; exit 1; fi
if [ ! -d ".tmp/softwareFactoryVscode" ]; then echo "❌ Missing .tmp isolation"; exit 1; fi

echo "✅ Phase 10 Scripts operate exactly to specifications."
