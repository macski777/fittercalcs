const { app, BrowserWindow, ipcMain, shell } = require("electron");
const fs = require("fs");
const path = require("path");

function picturesDir() {
  return path.join(app.getPath("pictures"), "FitterCalcs");
}

function safeName(name) {
  name = path.basename(name || "FitterCalcs-report.png");
  name = name.replace(/[^A-Za-z0-9._-]+/g, "_");
  if (!name.toLowerCase().endsWith(".png")) name += ".png";
  return name;
}

function decodePng(dataUrl) {
  const b64 = String(dataUrl || "").split(",").pop();
  return Buffer.from(b64, "base64");
}

function savePng(dataUrl, filename) {
  const dir = picturesDir();
  fs.mkdirSync(dir, { recursive: true });
  const dest = path.join(dir, safeName(filename));
  fs.writeFileSync(dest, decodePng(dataUrl));
  return dest;
}

function createWindow() {
  const win = new BrowserWindow({
    width: 480,
    height: 880,
    minWidth: 380,
    minHeight: 640,
    backgroundColor: "#14110F",
    autoHideMenuBar: true,
    icon: path.join(__dirname, "assets", "logo.png"),
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  });
  win.setMenuBarVisibility(false);
  win.loadFile(path.join(__dirname, "assets", "index.html"));
}

app.whenReady().then(createWindow);
app.on("window-all-closed", () => app.quit());

ipcMain.handle("savePng", (_e, dataUrl, filename) => {
  const dest = savePng(dataUrl, filename);
  return dest;
});

ipcMain.handle("emailPng", (_e, dataUrl, filename, subject, body) => {
  const dest = savePng(dataUrl, filename);
  const text = (body || "") + "\n\nChart saved to:\n" + dest;
  const url =
    "mailto:?subject=" +
    encodeURIComponent(subject || "FitterCalcs report") +
    "&body=" +
    encodeURIComponent(text);
  shell.openExternal(url);
  shell.showItemInFolder(dest);
  return dest;
});

ipcMain.handle("emailText", (_e, subject, body) => {
  const url =
    "mailto:?subject=" +
    encodeURIComponent(subject || "FitterCalcs report") +
    "&body=" +
    encodeURIComponent(body || "");
  shell.openExternal(url);
});

ipcMain.handle("toast", () => {});
ipcMain.handle("fullscreen", (e, on) => {
  const win = BrowserWindow.fromWebContents(e.sender);
  if (win) win.setFullScreen(!!on);
});
