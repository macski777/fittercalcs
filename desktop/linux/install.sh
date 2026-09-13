#!/usr/bin/env bash
# Install FitterCalcs for the current user on Linux (GTK + WebKit).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="${XDG_DATA_HOME:-$HOME/.local/share}/onlyfitters"
BIN="${XDG_BIN_HOME:-$HOME/.local/bin}"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"

mkdir -p "$DEST" "$BIN" "$APPS"
cp -f "$HERE/onlyfitters.py" "$HERE/index.html" "$HERE/logo.png" \
  "$HERE/wordmark.svg" "$HERE/wordmark.png" "$HERE/onlyfitters.png" "$DEST/"
chmod +x "$DEST/onlyfitters.py"

cat > "$BIN/fittercalcs" <<EOF
#!/usr/bin/env bash
exec python3 "$DEST/onlyfitters.py" "\$@"
EOF
chmod +x "$BIN/fittercalcs"
ln -sfn "$BIN/fittercalcs" "$BIN/onlyfitters"

cat > "$APPS/FitterCalcs.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=FitterCalcs
Comment=Field calculator for fire protection fitters
Exec=$BIN/fittercalcs
Icon=$DEST/onlyfitters.png
Terminal=false
Categories=Utility;Engineering;
StartupNotify=true
StartupWMClass=FitterCalcs
Keywords=pipe;sprinkler;annubar;flange;pump;fitter;tank;hydro;1851;
EOF
chmod +x "$APPS/FitterCalcs.desktop"
command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" >/dev/null 2>&1 || true

echo "Installed FitterCalcs for $USER"
echo "Run:  fittercalcs"
echo "Needs: python3, python-gobject (gi), GTK 3, WebKitGTK 4.1"
echo "Arch:  sudo pacman -S python-gobject webkit2gtk-4.1"
echo "Debian/Ubuntu: sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1"
