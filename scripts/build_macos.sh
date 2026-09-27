#!/bin/zsh
set -euo pipefail

cd "${0:A:h}/.."
if [[ "$(uname -m)" != "arm64" ]]; then
  print -u2 "Noki AI builds only on Apple Silicon Macs."
  exit 1
fi

python_bin="${PYTHON_BIN:-.venv/bin/python}"
"$python_bin" -m PyInstaller \
  --noconfirm --clean --windowed --onedir \
  --name "Noki AI" \
  --osx-bundle-identifier "com.nokit.noki-ai" \
  --icon "src/free_agent/desktop/assets/NokiAI.icns" \
  --add-data "src/free_agent/desktop/assets/app-icon.png:free_agent/desktop/assets" \
  --add-data "src/free_agent/desktop/assets/NokiAI.icns:free_agent/desktop/assets" \
  --add-data "src/free_agent/desktop/assets/portrait.png:free_agent/desktop/assets" \
  --add-data "src/free_agent/desktop/assets/logo.png:free_agent/desktop/assets" \
  --add-data "src/free_agent/desktop/assets/chevron.svg:free_agent/desktop/assets" \
  --add-data "src/free_agent/desktop/assets/BricolageGrotesque.ttf:free_agent/desktop/assets" \
  --add-data "src/free_agent/desktop/assets/OFL-BricolageGrotesque.txt:free_agent/desktop/assets" \
  "src/free_agent/desktop/__main__.py"

app_version="$("$python_bin" -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $app_version" "dist/Noki AI.app/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :CFBundleVersion string $app_version" "dist/Noki AI.app/Contents/Info.plist"
codesign --force --deep --sign - "dist/Noki AI.app"

print "Built: ${PWD}/dist/Noki AI.app"
