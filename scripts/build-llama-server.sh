#!/bin/bash
# Builds the pinned llama.cpp's llama-server for the sidecar, which starts
# it to embed with bge-m3 (#413). Built from source at a pinned tag whose
# archive is checked by sha256, with HTTPS and the web UI left out: the
# server only answers the sidecar on 127.0.0.1.
#
# macOS: one static binary with Metal shaders embedded, at
# src-tauri/binaries/llama-server-<triple>, the name Tauri's externalBin
# expects.
#
# Windows (release.yml, Git Bash, Vulkan SDK installed): llama.cpp's own
# release layout in src-tauri/binaries/llama-server/, which
# tauri.windows.conf.json bundles as a resource. llama-server.exe loads its
# backends from the DLLs beside it: the CPU variant that suits the machine,
# and Vulkan, skipped where no GPU driver provides vulkan-1.dll. The C
# runtime is linked in, so no Visual C++ redistributable is needed.
#
# llama.cpp's licence and those of the code it vendors land in
# src-tauri/binaries/llama-server-licenses/, for scripts/acknowledgements.py.
#
# A build is cached per triple and version of this script, so a new tag or
# flag builds afresh (~/.cache/unseen-servant/llama-server, or
# UNSEEN_LLAMA_CACHE); worktrees and re-runs copy instead of compiling.
# Needs cmake (brew install cmake).
set -euo pipefail

LLAMA_CPP_TAG=b11550
LLAMA_CPP_SHA256=06114fb71a31ca58709c6aece84c806e27321574af5830bdc16ddc7b1f0c2708

sha256() {
  if command -v sha256sum >/dev/null; then sha256sum "$1"; else shasum -a 256 "$1"; fi | cut -d' ' -f1
}

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BINARIES="$PROJECT_ROOT/src-tauri/binaries"
TRIPLE=$(rustc -vV | sed -n 's/^host: //p')
CACHE="${UNSEEN_LLAMA_CACHE:-$HOME/.cache/unseen-servant/llama-server}/$LLAMA_CPP_TAG-$TRIPLE-$(sha256 "$0" | cut -c1-12)"

if [ ! -d "$CACHE/bin" ]; then
  echo "==> Building llama-server $LLAMA_CPP_TAG for $TRIPLE..."
  WORK=$(mktemp -d)
  trap 'rm -rf "$WORK"' EXIT
  curl -fsSL -o "$WORK/src.tar.gz" \
    "https://github.com/ggml-org/llama.cpp/archive/refs/tags/$LLAMA_CPP_TAG.tar.gz"
  GOT=$(sha256 "$WORK/src.tar.gz")
  if [ "$GOT" != "$LLAMA_CPP_SHA256" ]; then
    echo "llama.cpp $LLAMA_CPP_TAG archive: sha256 $GOT, expected $LLAMA_CPP_SHA256" >&2
    exit 1
  fi
  tar xzf "$WORK/src.tar.gz" -C "$WORK"
  SRC="$WORK/llama.cpp-$LLAMA_CPP_TAG"

  FLAGS=(
    -DCMAKE_BUILD_TYPE=Release
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
    *apple-darwin) FLAGS+=(
      -DBUILD_SHARED_LIBS=OFF
      -DGGML_METAL=ON -DGGML_METAL_EMBED_LIBRARY=ON
      -DCMAKE_OSX_DEPLOYMENT_TARGET=13.3
    ) ;;
    # Backends as DLLs, as llama.cpp's Windows releases ship them.
    *windows*) FLAGS+=(
      -DBUILD_SHARED_LIBS=ON
      -DGGML_BACKEND_DL=ON -DGGML_CPU_ALL_VARIANTS=ON -DGGML_VULKAN=ON
      -DCMAKE_POLICY_DEFAULT_CMP0091=NEW -DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded
    ) ;;
  esac
  cmake -S "$SRC" -B "$WORK/build" "${FLAGS[@]}"
  # With GGML_BACKEND_DL, ggml depends on every backend, so this builds them.
  cmake --build "$WORK/build" --config Release --target llama-server -j

  BUILT=$(find "$WORK/build/bin" -name 'llama-server' -o -name 'llama-server.exe' | head -1)
  mkdir -p "$CACHE/licenses" "$CACHE/bin.partial"
  cp "$SRC/LICENSE" "$CACHE/licenses/LICENSE-llama.cpp"
  cp "$SRC"/licenses/* "$CACHE/licenses/"
  cp "$BUILT" "$CACHE/bin.partial/"
  case "$TRIPLE" in *windows*) cp "$(dirname "$BUILT")"/*.dll "$CACHE/bin.partial/" ;; esac
  mv "$CACHE/bin.partial" "$CACHE/bin"
fi

mkdir -p "$BINARIES"
case "$TRIPLE" in
  *windows*)
    OUT="$BINARIES/llama-server"
    rm -rf "$OUT"
    cp -R "$CACHE/bin" "$OUT"
    ;;
  *)
    OUT="$BINARIES/llama-server-$TRIPLE"
    cp "$CACHE/bin/llama-server" "$OUT"
    chmod +x "$OUT"
    ;;
esac
rm -rf "$BINARIES/llama-server-licenses"
cp -R "$CACHE/licenses" "$BINARIES/llama-server-licenses"
echo "==> $OUT"
