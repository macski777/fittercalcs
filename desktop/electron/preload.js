const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("FitterCalcsPC", true);
contextBridge.exposeInMainWorld("OnlyFitters", {
  savePng: (dataUrl, filename) => ipcRenderer.invoke("savePng", dataUrl, filename),
  emailPng: (dataUrl, filename, subject, body) =>
    ipcRenderer.invoke("emailPng", dataUrl, filename, subject, body),
  emailText: (subject, body) => ipcRenderer.invoke("emailText", subject, body),
  toast: (msg) => ipcRenderer.invoke("toast", msg),
  fullscreen: (on) => ipcRenderer.invoke("fullscreen", !!on)
});
