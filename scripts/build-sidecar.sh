#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SIDECAR_DIR="$PROJECT_ROOT/sidecar"
BINARIES_DIR="$PROJECT_ROOT/src-tauri/binaries"

# Determine target triple
ARCH=$(uname -m)
if [ "$ARCH" = "arm64" ]; then
  TARGET_TRIPLE="aarch64-apple-darwin"
elif [ "$ARCH" = "x86_64" ]; then
  TARGET_TRIPLE="x86_64-apple-darwin"
else
  echo "Unsupported architecture: $ARCH"
  exit 1
fi

echo "==> Building sidecar binaries for $TARGET_TRIPLE..."

cd "$SIDECAR_DIR"

# Sync the project venv (Python from .python-version) with the build group,
# which provides PyInstaller. Frozen so the release build matches uv.lock.
uv sync --frozen --group build

echo "==> Building legend-lore-sidecar (FastAPI server)..."
# --collect-all pulls in submodules + binaries + data files:
#  - pymupdf{,4llm}: ONNX layout-analyzer YAML/weights at
#    pymupdf/layout/resources/
#  - fastembed: cross-encoder ONNX model + tokenizer assets used by
#    the reranker
#  - symspellpy: frequency_dictionary_en_82_765.txt, read at runtime by
#    spelling.py's general-English guard — pure-Python module, but the
#    data file is not collected on its own
# Kept in sync with .github/workflows/release.yml.
uv run --frozen --no-sync pyinstaller --onefile --name legend-lore-sidecar server.py \
  --collect-all chromadb \
  --collect-all pymupdf \
  --collect-all pymupdf4llm \
  --collect-all fastembed \
  --collect-all symspellpy \
  --hidden-import uvicorn.logging \
  --hidden-import uvicorn.protocols.http \
  --hidden-import uvicorn.protocols.http.auto \
  --hidden-import uvicorn.protocols.http.h11_impl \
  --hidden-import uvicorn.protocols.http.httptools_impl \
  --hidden-import uvicorn.protocols.websockets \
  --hidden-import uvicorn.protocols.websockets.auto \
  --hidden-import uvicorn.protocols.websockets.wsproto_impl \
  --hidden-import uvicorn.protocols.websockets.websockets_impl \
  --hidden-import uvicorn.lifespan \
  --hidden-import uvicorn.lifespan.on \
  --hidden-import uvicorn.lifespan.off \
  --noconfirm --clean

echo "==> Building legend-lore-mcp (MCP server)..."
uv run --frozen --no-sync pyinstaller --onefile --name legend-lore-mcp mcp_server.py \
  --hidden-import mcp.server.fastmcp \
  --noconfirm --clean

echo "==> Placing binaries in src-tauri/binaries/..."
mkdir -p "$BINARIES_DIR"
cp "$SIDECAR_DIR/dist/legend-lore-sidecar" "$BINARIES_DIR/legend-lore-sidecar-$TARGET_TRIPLE"
cp "$SIDECAR_DIR/dist/legend-lore-mcp" "$BINARIES_DIR/legend-lore-mcp-$TARGET_TRIPLE"

echo "==> Done! Binaries placed at:"
ls -lh "$BINARIES_DIR/"
