#!/bin/bash
set -euo pipefail

if [ -z "${1:-}" ]; then
  echo "Usage: $0 <version>"
  echo "Example: $0 1.0.0"
  exit 1
fi

VERSION="$1"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "Bumping version to $VERSION..."

sed -i '' "s/\"version\": \".*\"/\"version\": \"$VERSION\"/" "$PROJECT_ROOT/package.json"
sed -i '' "s/\"version\": \".*\"/\"version\": \"$VERSION\"/" "$PROJECT_ROOT/src-tauri/tauri.conf.json"
sed -i '' "s/^version = \".*\"/version = \"$VERSION\"/" "$PROJECT_ROOT/src-tauri/Cargo.toml"

# Cargo.lock holds its own copy of legend-lore's version. Without this
# sync, the next `cargo build` after a bump rewrites the lockfile and
# the version-bump commit is left with a stale lock — easy to miss in
# review and mildly confusing for downstream `cargo build` users.
echo "Syncing Cargo.lock..."
( cd "$PROJECT_ROOT/src-tauri" && cargo update -p legend-lore --quiet )

# Verify every version file actually reflects $VERSION. set -euo pipefail
# would catch a sed failure but won't catch a sed that ran but matched
# nothing (silent no-op), and won't catch `cargo update` quietly
# refusing to bump because the manifest didn't actually change.
fail=0
check_version() {
  local label="$1"
  local got="$2"
  if [ "$got" != "$VERSION" ]; then
    echo "FAIL: $label has version '$got', expected '$VERSION'"
    fail=1
  fi
}

pkg_json_v=$(grep '"version"' "$PROJECT_ROOT/package.json" | head -1 | sed -E 's/.*"version": *"([^"]+)".*/\1/')
tauri_v=$(grep '"version"' "$PROJECT_ROOT/src-tauri/tauri.conf.json" | head -1 | sed -E 's/.*"version": *"([^"]+)".*/\1/')
cargo_toml_v=$(grep '^version = ' "$PROJECT_ROOT/src-tauri/Cargo.toml" | head -1 | sed -E 's/^version *= *"([^"]+)".*/\1/')
cargo_lock_v=$(awk '/^name = "legend-lore"$/{getline; print; exit}' "$PROJECT_ROOT/src-tauri/Cargo.lock" | sed -E 's/^version *= *"([^"]+)".*/\1/')

check_version "package.json"        "$pkg_json_v"
check_version "src-tauri/tauri.conf.json" "$tauri_v"
check_version "src-tauri/Cargo.toml"      "$cargo_toml_v"
check_version "src-tauri/Cargo.lock"      "$cargo_lock_v"

if [ "$fail" -ne 0 ]; then
  echo
  echo "Version mismatch detected. Aborting."
  exit 1
fi

echo "Updated:"
echo "  package.json        $pkg_json_v"
echo "  tauri.conf.json     $tauri_v"
echo "  Cargo.toml          $cargo_toml_v"
echo "  Cargo.lock          $cargo_lock_v"
