#!/usr/bin/env bash
set -euo pipefail

sudo dnf install \
  gnome-builder \
  meson \
  ninja-build \
  python3 \
  python3-gobject \
  gtk4 \
  gtk4-devel \
  libadwaita \
  libadwaita-devel \
  glib2-devel \
  desktop-file-utils \
  appstream \
  flatpak-builder \
  inotify-tools \
  sassc \
  mutter-devkit \
  gnome-shell-extension-user-theme \
  gnome-shell-extension-dash-to-dock

echo
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$HOME/.local/bin"
ln -sfn "$ROOT/dev-shell-preview.sh" "$HOME/.local/bin/fedora-nova-shell-preview"

echo
echo "Hotovo."
echo "Builder projekt: $ROOT/meson.build"
echo "Nested Shell preview:"
echo "  fedora-nova-shell-preview tech"
