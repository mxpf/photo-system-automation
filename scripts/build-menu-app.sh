#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR="$PROJECT_DIR/dist/Photo System.app"
CONTENTS="$APP_DIR/Contents"
MACOS="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources"

mkdir -p "$MACOS" "$RESOURCES"
cp "$PROJECT_DIR/app/Info.plist" "$CONTENTS/Info.plist"

swiftc \
  -parse-as-library \
  "$PROJECT_DIR/app/PhotoSystemMenuApp.swift" \
  -o "$MACOS/Photo System" \
  -framework Cocoa

chmod +x "$MACOS/Photo System"
echo "$APP_DIR"
