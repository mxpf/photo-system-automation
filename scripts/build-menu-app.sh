#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR="$PROJECT_DIR/dist/Photo System.app"
CONTENTS="$APP_DIR/Contents"
MACOS="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources"
FONTS="$RESOURCES/Fonts"

mkdir -p "$MACOS" "$RESOURCES" "$FONTS"
cp "$PROJECT_DIR/app/Info.plist" "$CONTENTS/Info.plist"

find "$FONTS" -type f \( -name '*.otf' -o -name '*.ttf' \) -delete
for font in "$HOME"/Library/Fonts/ABCDiatypeTrial-*.otf "$HOME"/Library/Fonts/*Diatype*.otf "$HOME"/Library/Fonts/*Diatype*.ttf; do
  if [ -f "$font" ]; then
    cp "$font" "$FONTS/"
  fi
done

swiftc \
  -parse-as-library \
  "$PROJECT_DIR/app/PhotoSystemMenuApp.swift" \
  -o "$MACOS/Photo System" \
  -framework Cocoa

chmod +x "$MACOS/Photo System"
codesign --force --deep --sign - "$APP_DIR" >/dev/null 2>&1 || true
echo "Embedded fonts:"
find "$FONTS" -maxdepth 1 -type f -print | sed 's#^#  #'
echo "$APP_DIR"
