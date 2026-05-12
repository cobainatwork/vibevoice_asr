#!/usr/bin/env bash
# Download Audio-Denoiser-ONNX models for ASR pre-processing.
# Run once after `git clone`.
#
# WARNING: Direct download URLs are not yet publicly available from upstream.
# The Audio-Denoiser-ONNX repo (https://github.com/DakeQQ/Audio-Denoiser-ONNX)
# currently has no GitHub releases and no public HuggingFace mirror URLs.
#
# Options:
#   1. Export from source: see vendor/denoiser/README.md "方法 1"
#   2. Update GTCRN_URL / ZIPENHANCER_URL below when upstream publishes direct links.

set -euo pipefail

VENDOR_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../vendor/denoiser" && pwd)"

# === URLs (update when upstream provides direct download links) ===
# Currently set to placeholder — upstream has no public release assets.
GTCRN_URL="MANUAL"
ZIPENHANCER_URL="MANUAL"

echo "=== Audio-Denoiser-ONNX model downloader ==="
echo "Target directory: $VENDOR_DIR"
echo ""

if [ "$GTCRN_URL" = "MANUAL" ] || [ "$ZIPENHANCER_URL" = "MANUAL" ]; then
    echo "WARNING: Direct download URLs are not available yet."
    echo ""
    echo "Please obtain model files manually:"
    echo "  1. Clone https://github.com/DakeQQ/Audio-Denoiser-ONNX"
    echo "  2. Run Export_GTCRN.py and Export_ZipEnhancer.py"
    echo "  3. Copy resulting .onnx files to: $VENDOR_DIR/"
    echo "     - GTCRN.onnx"
    echo "     - ZipEnhancer.onnx"
    echo ""
    echo "See vendor/denoiser/README.md for detailed instructions."
    exit 1
fi

cd "$VENDOR_DIR"

echo "Downloading GTCRN to $VENDOR_DIR/GTCRN.onnx ..."
wget -O GTCRN.onnx "$GTCRN_URL"

echo "Downloading ZipEnhancer to $VENDOR_DIR/ZipEnhancer.onnx ..."
wget -O ZipEnhancer.onnx "$ZIPENHANCER_URL"

echo ""
echo "Done. Models in $VENDOR_DIR/"
ls -lh "$VENDOR_DIR"/*.onnx
