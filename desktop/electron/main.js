const { app, BrowserWindow, dialog, ipcMain, shell } = require("electron");
const { spawn } = require("child_process");
const fs = require("fs");
const https = require("https");
const path = require("path");
const updater = require("./update.js");

function serverUrl() {
  const candidates = [
    path.join(__dirname, "server.url"),
    path.join(__dirname, "assets", "server.url"),
    path.join(__dirname, "..", "..", "app", "src", "main", "assets", "server.url")
  ];
  for (const file of candidates) {
    try {
      const line = fs.readFileSync(file, "utf8").trim().split(/\r?\n/)[0].trim();
      if (line.startsWith("https://") && !line.includes(" ") && line.length < 200) {
        return line.endsWith("/") ? line : line + "/";
      }
    } catch (e) {}
  }
  return "";
}

function serverUp(url) {
  const once = () => new Promise((resolve) => {
    const req = https.get(url + "api/setup", { timeout: 6000 }, (res) => {
      res.resume();
      resolve(res.statusCode >= 200 && res.statusCode < 500);
    });
    req.on("error", () => resolve(false));
    req.on("timeout", () => {
      req.destroy();
      resolve(false);
    });
  });
  return (async () => {
    for (let i = 0; i < 3; i++) {
      if (await once()) return true;
    }
    return false;
  })();
}

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

let pendingUpdate = null;
let downloading = false;

function showBanner(win, version, notes) {
  if (!win || win.isDestroyed()) return Promise.resolve();
  const js =
    "if(window.FitterCalcsUpdate)FitterCalcsUpdate.show(" +
    JSON.stringify(version) + "," +
    JSON.stringify(notes || "") + ")";
  return win.webContents.executeJavaScript(js).catch(() => {});
}

function setBannerText(win, title, note) {
  if (!win || win.isDestroyed()) return Promise.resolve();
  const js =
    "(()=>{const b=document.getElementById('updateBanner');" +
    "const t=document.getElementById('updateTitle');" +
    "const n=document.getElementById('updateNotes');" +
    "if(!b)return;if(t)t.textContent=" + JSON.stringify(title) + ";" +
    "if(n)n.textContent=" + JSON.stringify(note) + ";" +
    "b.classList.remove('hidden');})()";
  return win.webContents.executeJavaScript(js).catch(() => {});
}

async function checkForUpdate(win, fromUser) {
  try {
    const info = await updater.fetchUpdate();
    const have = updater.localVersionCode();
    if (info.versionCode <= have) {
      pendingUpdate = null;
      if (fromUser) {
        dialog.showMessageBox(win, {
          type: "info",
          message: "FitterCalcs is up to date (v" + app.getVersion().replace(/\.0$/, "") + ")"
        });
      }
      return;
    }
    pendingUpdate = info;
    await showBanner(win, info.versionName, info.notes);
  } catch (e) {
    if (fromUser) {
      dialog.showMessageBox(win, {
        type: "error",
        message: "Could not check for an update. Check the internet connection."
      });
    }
  }
}

function psQuote(s) {
  if (/[\r\n\0"&|<>^]/.test(s)) throw new Error("Bad path");
  return "'" + String(s).replace(/'/g, "''") + "'";
}

function applyPortableUpdate(portableExe, downloaded) {
  const pid = process.pid;
  const ps1 = [
    "$pidToWait = " + pid,
    "$newFile = " + psQuote(downloaded),
    "$target = " + psQuote(portableExe),
    "while (Get-Process -Id $pidToWait -ErrorAction SilentlyContinue) { Start-Sleep -Milliseconds 400 }",
    "Start-Sleep -Milliseconds 800",
    "$ok = $false",
    "foreach ($i in 1..40) {",
    "  try {",
    "    Move-Item -LiteralPath $newFile -Destination $target -Force -ErrorAction Stop",
    "    $ok = $true",
    "    break",
    "  } catch { Start-Sleep -Milliseconds 500 }",
    "}",
    "if (Test-Path -LiteralPath $target) { Start-Process -FilePath $target }"
  ].join("\r\n");
  const dir = path.dirname(downloaded);
  const ps1Path = path.join(dir, "FitterCalcs-apply-update.ps1");
  const batPath = path.join(dir, "FitterCalcs-apply-update.bat");
  fs.writeFileSync(ps1Path, ps1, "utf8");
  fs.writeFileSync(batPath, "@echo off\r\npowershell.exe -NoProfile -ExecutionPolicy Bypass -File \"" + ps1Path + "\"\r\n", "utf8");
  const child = spawn("cmd.exe", ["/d", "/c", "start", "", batPath], {
    detached: true,
    stdio: "ignore",
    windowsHide: true
  });
  child.unref();
}

async function installUpdate(win) {
  if (downloading) return;
  if (!pendingUpdate) {
    await checkForUpdate(win, true);
    return;
  }
  const url = updater.winDownloadUrl(pendingUpdate);
  if (!url) {
    dialog.showMessageBox(win, { type: "error", message: "This update has no Windows download." });
    return;
  }
  const portable = process.env.PORTABLE_EXECUTABLE_FILE;
  if (process.platform !== "win32" || !portable) {
    await shell.openExternal(url);
    return;
  }
  downloading = true;
  const name = pendingUpdate.versionName || "update";
  try {
    await setBannerText(win, "Downloading FitterCalcs " + name, "This can take a minute. The app will restart.");
    const dest = path.join(app.getPath("temp"), "FitterCalcs-Setup-download.exe");
    await updater.downloadFile(url, dest, (got, total) => {
      const pct = Math.min(100, Math.round((got / total) * 100));
      setBannerText(win, "Downloading FitterCalcs " + name, pct + "% — the app will restart when it finishes.");
    });
    applyPortableUpdate(portable, dest);
    app.quit();
  } catch (e) {
    downloading = false;
    dialog.showMessageBox(win, {
      type: "error",
      message: "Download failed.",
      detail: e && e.message ? e.message : String(e)
    });
  }
}

async function createWindow() {
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
  const localFile = path.join(__dirname, "assets", "index.html");
  const remote = serverUrl();
  let openedServer = false;
  if (remote && await serverUp(remote)) {
    openedServer = true;
    win.loadURL(remote);
  } else {
    win.loadFile(localFile);
  }
  win.webContents.on("did-fail-load", (_event, code, _desc, _url, isMainFrame) => {
    if (!isMainFrame || code === -3 || !openedServer) return;
    openedServer = false;
    win.loadFile(localFile);
  });
  win.webContents.on("did-finish-load", () => checkForUpdate(win, false));
  return win;
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
ipcMain.handle("checkUpdate", (e) => checkForUpdate(BrowserWindow.fromWebContents(e.sender), true));
ipcMain.handle("installUpdate", (e) => installUpdate(BrowserWindow.fromWebContents(e.sender)));
ipcMain.handle("fullscreen", (e, on) => {
  const win = BrowserWindow.fromWebContents(e.sender);
  if (win) win.setFullScreen(!!on);
});
