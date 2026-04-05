#!/usr/bin/env bash
# ============================================================
# Render Build Script
# ============================================================
# Render runs this during deployment. It installs Python deps
# and copies the ML model files into the backend directory.
# ============================================================
set -o errexit

echo "=== Installing Python dependencies ==="
cd flask_backend
pip install -r requirements.txt

echo "=== Copying ML models ==="
mkdir -p ml_models
cp -r ../ml/model/* ml_models/ 2>/dev/null || echo "No ML models found (non-fatal)"

echo "=== Creating upload directory ==="
mkdir -p uploads/screenshots

echo "=== Build complete ==="
