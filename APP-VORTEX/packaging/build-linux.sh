#!/usr/bin/env bash
# Build the Linux onedir distribution of the Vortex app.
# Run from APP-VORTEX/: ./packaging/build-linux.sh
# Requires: pip install pyinstaller (inside the project venv).
set -euo pipefail
cd "$(dirname "$0")/.."

pyinstaller \
    --name vortex-app \
    --onedir \
    --windowed \
    --paths ../PROTO-VORTEX-01A/generated \
    --hidden-import vortex_protocol \
    --noconfirm \
    vortex_app/__main__.py

echo "dist/vortex-app/ ready."
# ponytail: AppImage step skipped — wrap dist/vortex-app with appimagetool
# (linuxdeploy) when distribution outside dev machines starts.
