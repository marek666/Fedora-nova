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
echo "Hotovo."
echo "Builder projekt: ./meson.build"
echo "Nested Shell preview z aktuálního checkoutu:"
echo "  ./dev-shell-preview.sh tech"
