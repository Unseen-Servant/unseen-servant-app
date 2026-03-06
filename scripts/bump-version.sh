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

echo "Updated:"
grep '"version"' "$PROJECT_ROOT/package.json" | head -1
grep '"version"' "$PROJECT_ROOT/src-tauri/tauri.conf.json" | head -1
grep '^version' "$PROJECT_ROOT/src-tauri/Cargo.toml"
