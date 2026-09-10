#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
project_root="$(pwd -P)"
if [[ ! -f "$project_root/main.py" || ! -f "$project_root/SolarTimeDistanceExplorer.spec" ]]; then
    echo "Refusing to build outside the Solar Time-Distance Explorer project root." >&2
    exit 2
fi

python_command="${PYTHON_COMMAND:-python3}"
if [[ ! -x ".venv/bin/python" ]]; then
    "$python_command" -m venv .venv
fi
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
if [[ "${SKIP_TESTS:-0}" != "1" ]]; then
    QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
fi

for target in "$project_root/build" "$project_root/dist"; do
    case "$target" in
        "$project_root"/*) rm -rf -- "$target" ;;
        *) echo "Unsafe build target: $target" >&2; exit 2 ;;
    esac
done
.venv/bin/python -m PyInstaller --noconfirm --clean SolarTimeDistanceExplorer.spec

version="$(.venv/bin/python -c 'from app.version import __version__; print(__version__)')"
mkdir -p release
system="$(uname -s)"
machine="$(uname -m)"
if [[ "$system" == "Darwin" ]]; then
    if [[ ! -d "dist/SolarTimeDistanceExplorer.app" ]]; then
        echo "Expected macOS application bundle was not produced." >&2
        exit 3
    fi
    QT_QPA_PLATFORM=minimal "dist/SolarTimeDistanceExplorer.app/Contents/MacOS/SolarTimeDistanceExplorer" --smoke-test
    architecture="x64"
    [[ "$machine" == "arm64" ]] && architecture="arm64"
    archive="release/SolarTimeDistanceExplorer-${version}-macOS-${architecture}.zip"
    rm -f -- "$archive"
    ditto -c -k --sequesterRsrc --keepParent "dist/SolarTimeDistanceExplorer.app" "$archive"
    shasum -a 256 "$archive" > "${archive%.zip}.sha256.txt"
else
    if [[ ! -x "dist/SolarTimeDistanceExplorer/SolarTimeDistanceExplorer" ]]; then
        echo "Expected Linux executable was not produced." >&2
        exit 3
    fi
    QT_QPA_PLATFORM=offscreen "dist/SolarTimeDistanceExplorer/SolarTimeDistanceExplorer" --smoke-test
    cp README.md "dist/SolarTimeDistanceExplorer/"
    mkdir -p "dist/SolarTimeDistanceExplorer/docs"
    cp docs/UserGuide.md "dist/SolarTimeDistanceExplorer/docs/"
    architecture="x64"
    [[ "$machine" == "aarch64" || "$machine" == "arm64" ]] && architecture="arm64"
    archive="release/SolarTimeDistanceExplorer-${version}-Linux-${architecture}.tar.gz"
    rm -f -- "$archive"
    tar -C dist -czf "$archive" SolarTimeDistanceExplorer
    sha256sum "$archive" > "${archive%.tar.gz}.sha256.txt"
fi
echo "Native package created: $archive"
