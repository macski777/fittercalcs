Windows desktop build (Electron).

From this folder, after copying app assets into assets/:

    npm install
    npx electron-builder --win portable

That writes dist/FitterCalcs 2.29.0.exe — a single portable Windows app.
NSIS "Setup" needs Wine; portable does not.
