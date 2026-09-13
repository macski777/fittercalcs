FitterCalcs for Linux
=====================

GTK + WebKit desktop build of the same field calculator as the Android app.

Install (current user, no root):

    chmod +x install.sh
    ./install.sh

Then open FitterCalcs from the app menu, or run:

    fittercalcs

Requires Python 3 with GObject, GTK 3, and WebKitGTK 4.1:

    Arch / Omarchy:  sudo pacman -S python-gobject webkit2gtk-4.1
    Debian/Ubuntu:   sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1
