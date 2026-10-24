#!/bin/bash
# Builds the pinned llama.cpp's llama-server into
# src-tauri/binaries/llama-server-<triple>, the name Tauri's externalBin
# expects. The sidecar starts it to embed with bge-m3 (#413).
#
# macOS: one static binary, Metal shaders embedded. Windows (release.yml,
# Git Bash): one static exe with the Vulkan and CPU backends; the Vulkan
# loader comes with the GPU driver. Built from source at a pinned tag whose
# archive is checked by sha256, with HTTPS and the web UI left out: the
# server only answers the sidecar on 127.0.0.1.
#
# A build is cached per triple and version of this script, so a new tag or
# flag builds afresh (~/.cache/unseen-servant/llama-server, or
# UNSEEN_LLAMA_CACHE); worktrees and re-runs copy instead of compiling.
# Needs cmake (brew install cmake).
set -euo pipefail

LLAMA_CPP_TAG=b11550
LLAMA_CPP_SHA256=06114fb71a31ca58709c6aece84c806e27321574af5830bdc16ddc7b1f0c2708

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TRIPLE=$(rustc -vV | sed -n 's/^host: //p')
EXT=""
case "$TRIPLE" in *windows*) EXT=".exe" ;; esac
SCRIPT_HASH=$(shasum -a 256 "$0" | cut -c1-12)
CACHE="${UNSEEN_LLAMA_CACHE:-$HOME/.cache/unseen-servant/llama-server}/$LLAMA_CPP_TAG-$TRIPLE-$SCRIPT_HASH"
OUT="$PROJECT_ROOT/src-tauri/binaries/llama-server-$TRIPLE$EXT"

if [ ! -f "$CACHE/llama-server$EXT" ]; then
  echo "==> Building llama-server $LLAMA_CPP_TAG for $TRIPLE..."
  WORK=$(mktemp -d)
  trap 'rm -rf "$WORK"' EXIT
  curl -fsSL -o "$WORK/src.tar.gz" \
    "https://github.com/ggml-org/llama.cpp/archive/refs/tags/$LLAMA_CPP_TAG.tar.gz"
  GOT=$(shasum -a 256 "$WORK/src.tar.gz" | cut -d' ' -f1)
  if [ "$GOT" != "$LLAMA_CPP_SHA256" ]; then
    echo "llama.cpp $LLAMA_CPP_TAG archive: sha256 $GOT, expected $LLAMA_CPP_SHA256" >&2
    exit 1
  fi
  tar xzf "$WORK/src.tar.gz" -C "$WORK"

  FLAGS=(
    -DCMAKE_BUILD_TYPE=Release
    -DBUILD_SHARED_LIBS=OFF
    -DGGML_NATIVE=OFF
    # ggml's own thread pool instead: OpenMP would link Homebrew's libomp
    # on macOS and need vcomp140.dll beside the exe on Windows.
    -DGGML_OPENMP=OFF
    -DLLAMA_BUILD_TESTS=OFF
    -DLLAMA_BUILD_EXAMPLES=OFF
    -DLLAMA_BUILD_SERVER=ON
    -DLLAMA_OPENSSL=OFF
    -DLLAMA_USE_PREBUILT_UI=OFF
  )
  case "$TRIPLE" in
    # 13.3 is the floor llama.cpp's own macOS releases build for.
    *apple-darwin) FLAGS+=(-DGGML_METAL=ON -DGGML_METAL_EMBED_LIBRARY=ON -DCMAKE_OSX_DEPLOYMENT_TARGET=13.3) ;;
    *windows*) FLAGS+=(-DGGML_VULKAN=ON) ;;
  esac
  cmake -S "$WORK/llama.cpp-$LLAMA_CPP_TAG" -B "$WORK/build" "${FLAGS[@]}"
  cmake --build "$WORK/build" --config Release --target llama-server -j

  BUILT=$(find "$WORK/build/bin" -name "llama-server$EXT" -type f | head -1)
  mkdir -p "$CACHE"
  cp "$BUILT" "$CACHE/llama-server$EXT"
fi

mkdir -p "$(dirname "$OUT")"
cp "$CACHE/llama-server$EXT" "$OUT"
chmod +x "$OUT"
echo "==> $OUT"
