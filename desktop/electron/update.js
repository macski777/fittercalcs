const fs = require("fs");
const https = require("https");
const path = require("path");

const JSON_URL = "https://raw.githubusercontent.com/macski777/fittercalcs/main/update.json";
const WIN_ASSET = "FitterCalcs-Setup.exe";
const REDIR_HOSTS = new Set([
  "github.com",
  "release-assets.githubusercontent.com",
  "objects.githubusercontent.com",
  "github-releases.githubusercontent.com"
]);

function localVersionCode() {
  try {
    return Number(require("./package.json").versionCode) || 0;
  } catch (e) {
    return 0;
  }
}

function allowedWinUrl(url) {
  let u;
  try {
    u = new URL(url);
  } catch (e) {
    return false;
  }
  if (u.protocol !== "https:" || u.hostname !== "github.com" || u.username || u.password) return false;
  return /^\/macski777\/fittercalcs\/releases\/download\/v\d+\.\d+\/FitterCalcs-Setup\.exe$/.test(u.pathname);
}

function winDownloadUrl(info) {
  if (!info) return "";
  if (info.winUrl) return allowedWinUrl(info.winUrl) ? info.winUrl : "";
  if (!/^\d+\.\d+$/.test(info.versionName || "")) return "";
  const url = "https://github.com/macski777/fittercalcs/releases/download/v" + info.versionName + "/" + WIN_ASSET;
  return allowedWinUrl(url) ? url : "";
}

function allowedHop(url) {
  let u;
  try {
    u = new URL(url);
  } catch (e) {
    return false;
  }
  if (u.protocol !== "https:") return false;
  if (REDIR_HOSTS.has(u.hostname)) return true;
  return u.hostname.endsWith(".githubusercontent.com");
}

function request(url, redirects, onResponse) {
  return new Promise((resolve, reject) => {
    let settled = false;
    const ok = (v) => { if (!settled) { settled = true; resolve(v); } };
    const bad = (e) => { if (!settled) { settled = true; reject(e); } };
    if (redirects > 5) return bad(new Error("Too many redirects"));
    if (!allowedHop(url)) return bad(new Error("Blocked download host"));
    const req = https.get(url, {
      headers: { "User-Agent": "FitterCalcs", Accept: "*/*" }
    }, (res) => {
      const code = res.statusCode || 0;
      if (code >= 300 && code < 400 && res.headers.location) {
        res.resume();
        let next;
        try {
          next = new URL(res.headers.location, url).href;
        } catch (e) {
          bad(e);
          return;
        }
        ok(request(next, redirects + 1, onResponse));
        return;
      }
      if (code < 200 || code >= 300) {
        res.resume();
        bad(new Error("HTTP " + code));
        return;
      }
      onResponse(res, req, ok, bad);
    });
    req.on("error", (e) => bad(e));
    req.setTimeout(60000, () => req.destroy(new Error("Timed out")));
  });
}

function fetchUpdate() {
  return request(JSON_URL, 0, (res, _req, resolve, reject) => {
    const chunks = [];
    res.on("data", (c) => chunks.push(c));
    res.on("end", () => {
      try {
        const o = JSON.parse(Buffer.concat(chunks).toString("utf8"));
        const versionCode = Number(o.versionCode);
        if (!Number.isFinite(versionCode)) throw new Error("Bad version");
        resolve({
          versionCode: versionCode,
          versionName: String(o.versionName || ""),
          notes: String(o.notes || ""),
          winUrl: String(o.winUrl || "")
        });
      } catch (e) {
        reject(e);
      }
    });
    res.on("error", reject);
  });
}

function readPrefix(url, n) {
  return request(url, 0, (res, req, resolve, reject) => {
    const chunks = [];
    let settled = false;
    const finish = (buf) => {
      if (settled) return;
      settled = true;
      req.destroy();
      resolve(buf);
    };
    res.on("data", (c) => {
      chunks.push(c);
      const got = Buffer.concat(chunks);
      if (got.length >= n) finish(got.subarray(0, n));
    });
    res.on("end", () => finish(Buffer.concat(chunks).subarray(0, n)));
    res.on("error", (e) => {
      if (!settled) reject(e);
    });
  });
}

function downloadFile(url, dest, onProgress) {
  const tmp = dest + ".part";
  return request(url, 0, (res, req, resolve, reject) => {
    const total = Number(res.headers["content-length"]) || 0;
    if (total > 200 * 1024 * 1024) {
      res.resume();
      reject(new Error("Download too large"));
      return;
    }
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    const out = fs.createWriteStream(tmp);
    let got = 0;
    let lastPct = -1;
    let failed = false;
    const fail = (err) => {
      if (failed) return;
      failed = true;
      req.destroy();
      out.destroy();
      fs.unlink(tmp, () => reject(err));
    };
    res.on("data", (c) => {
      got += c.length;
      if (got > 200 * 1024 * 1024) {
        fail(new Error("Download too large"));
        return;
      }
      if (!out.write(c)) res.pause();
      if (onProgress && total) {
        const pct = Math.floor((got / total) * 100);
        if (pct !== lastPct) {
          lastPct = pct;
          onProgress(got, total);
        }
      }
    });
    out.on("drain", () => res.resume());
    res.on("end", () => {
      if (failed) return;
      out.end(() => {
        if (failed) return;
        fs.stat(tmp, (err, st) => {
          if (err) return reject(err);
          if (st.size < 8 * 1024 * 1024) {
            fs.unlink(tmp, () => reject(new Error("Download too small")));
            return;
          }
          const fd = fs.openSync(tmp, "r");
          const magic = Buffer.alloc(2);
          fs.readSync(fd, magic, 0, 2, 0);
          fs.closeSync(fd);
          if (magic[0] !== 0x4d || magic[1] !== 0x5a) {
            fs.unlink(tmp, () => reject(new Error("Download is not a Windows app")));
            return;
          }
          fs.renameSync(tmp, dest);
          resolve(dest);
        });
      });
    });
    res.on("error", fail);
    out.on("error", fail);
  });
}

module.exports = {
  JSON_URL,
  localVersionCode,
  allowedWinUrl,
  winDownloadUrl,
  fetchUpdate,
  readPrefix,
  downloadFile
};
