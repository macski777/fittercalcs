function setupFanTest() {
  if (!window.FanCalc || document.getElementById("page-fantest").dataset.ready) return;
  document.getElementById("page-fantest").dataset.ready = "1";
  const $ = (id) => document.getElementById("ft" + id);
  let standard = "2015";
  let mixing = "descending";
  let pressureReg = "yes";
  let minBasis = "over13";
  let llfOverride = "no";
  let depressOmitted = "no";
  let agentName = FanCalc.SKY_AUS.agent;

  function chipGroup(id, set) {
    const host = $(id);
    host.querySelectorAll("button").forEach((b) => {
      b.onclick = () => {
        set(b.getAttribute("data-v"));
        host.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
        renderFan();
      };
    });
  }

  function pointTable(id, points) {
    const rows = points && points.length ? points.slice() : [{}, {}, {}, {}, {}];
    while (rows.length < 5) rows.push({});
    $(id).innerHTML = "<tr><th>Pa</th><th>Fan L/s</th></tr>" + rows.slice(0, 5).map((pt, i) =>
      "<tr><td><input data-i=\"" + i + "\" data-k=\"p\" type=\"number\" inputmode=\"decimal\" step=\"0.1\" value=\"" + (pt.p != null ? pt.p : "") + "\" /></td>" +
      "<td><input data-i=\"" + i + "\" data-k=\"q\" type=\"number\" inputmode=\"decimal\" step=\"0.1\" value=\"" + (pt.q != null ? pt.q : "") + "\" /></td></tr>"
    ).join("");
    $(id).querySelectorAll("input").forEach((el) => el.addEventListener("input", renderFan));
  }

  function readPoints(id) {
    const pts = [{}, {}, {}, {}, {}];
    $(id).querySelectorAll("input").forEach((el) => {
      pts[+el.dataset.i][el.dataset.k] = el.value;
    });
    return pts;
  }

  function fmt(n, d) {
    if (!Number.isFinite(n)) return "—";
    return n.toFixed(d);
  }

  function stat(label, value, small, wide, cls) {
    return "<div class=\"stat" + (wide ? " wide" : "") + (cls ? " " + cls : "") + "\"><label>" + label + "</label><b>" + value + "</b>" + (small ? "<small> " + small + "</small>" : "") + "</div>";
  }

  function formInput() {
    return {
      agent: agentName,
      standard: standard,
      mixing: mixing,
      pressureReg: pressureReg,
      minBasis: minBasis,
      llfOverride: llfOverride,
      llfPct: $("llfPct").value,
      depressOmitted: depressOmitted,
      insideC: $("insideC").value,
      outsideC: $("outsideC").value,
      designC: $("designC").value,
      atmBar: $("atmBar").value,
      biasTest: $("biasTest").value,
      biasHold: $("biasHold").value,
      floodedH: $("floodedH").value,
      volume: $("volume").value,
      minHeight: $("minHeight").value,
      mass: $("mass").value,
      roomStrength: $("roomStrength").value,
      dischargeS: $("dischargeS").value,
      pressPoints: readPoints("pressPts"),
      depressPoints: readPoints("depPts")
    };
  }

  function renderFan() {
    $("llfWrap").classList.toggle("hidden", llfOverride !== "yes");
    $("depPts").classList.toggle("hidden", depressOmitted === "yes");
    const res = FanCalc.calculate(formInput());
    if (res.error) {
      $("out").innerHTML = stat("Hold time", "—", res.error, true);
      $("warn").textContent = "";
      return;
    }
    const passCls = res.pass ? "hc-pass" : "hc-fail";
    const ventIn = res.ventIn == null ? "Not required" : fmt(res.ventIn, 3) + " m²";
    const addIn = res.addIn == null ? "Not required" : (res.addIn === 0 ? "Nil" : fmt(res.addIn, 3) + " m²");
    const addOut = res.addOut === 0 ? "Nil" : fmt(res.addOut, 3) + " m²";
    $("out").innerHTML = [
      stat("Hold time", fmt(res.holdMin, 2) + " min", (res.pass ? "PASS" : "FAIL") + " · need " + res.holdLimit + " min", true, passCls),
      stat("Initial concentration", fmt(res.ci, 2) + " %", "from installed mass"),
      stat("Minimum concentration", fmt(res.cmin, 2) + " %", "design " + fmt(res.design, 1) + "% · extinguishing " + fmt(res.extinguishing, 2) + "%"),
      stat("Required agent mass", fmt(res.reqMass, 2) + " kg", "installed " + $("mass").value + " kg"),
      stat("Equivalent interface", fmt(res.He, 2) + " m", res.iso2015 ? "ISO 14520-1:2015" : "ISO 14520-1:2006"),
      stat("Leakage exponent n", fmt(res.n, 3), "r press " + fmt(res.rPress, 3) + (res.rDep == null ? "" : " · r depress " + fmt(res.rDep, 3))),
      stat("Leakage constant k1", fmt(res.k1PerHour, 1), "m³/h at the reference fit"),
      stat("ELA at 10 Pa", fmt(res.elaCm2, 0) + " cm²", "average equivalent leakage area"),
      stat("Lower leakage fraction", fmt(res.F * 100, 0) + " %", res.mixing ? "continuous mixing" : "descending interface"),
      stat("Outward vent required", fmt(res.ventOut, 3) + " m²", "additional " + addOut),
      stat("Inward vent required", ventIn, "additional " + addIn)
    ].join("");
    const notes = [];
    if (!res.biasOk) notes.push("Bias pressure during the hold can reverse the column flow. The hold-time equation is not valid on these figures.");
    if (Number($("mass").value) + 0.05 < res.reqMass) notes.push("Installed mass is below the mass required for the design concentration.");
    $("warn").textContent = notes.join(" ");
    drawFanLeak();
  }

  function fanSeries(id) {
    const pts = readPoints(id).map((p) => ({ q: parseFloat(p.p), p: parseFloat(p.q) })).filter((p) => Number.isFinite(p.q) && Number.isFinite(p.p));
    pts.sort((a, b) => a.q - b.q);
    const out = [];
    pts.forEach((p) => {
      if (out.length && Math.abs(out[out.length - 1].q - p.q) < 1e-6) out[out.length - 1] = p;
      else out.push(p);
    });
    return out;
  }

  function niceAxis(max, target) {
    const m = Math.max(max, 1);
    const raw = m / target;
    const pow = Math.pow(10, Math.floor(Math.log10(raw)));
    const n = raw / pow;
    const step = n <= 1 ? pow : n <= 2 ? 2 * pow : n <= 5 ? 5 * pow : 10 * pow;
    return { step: step, max: Math.ceil(m / step) * step };
  }

  function drawFanOn(ctx, w, h, press, dep) {
    const padL = 78, padR = 28, padT = 52, padB = 64;
    ctx.fillStyle = "#f4ede4";
    ctx.fillRect(0, 0, w, h);
    const all = press.concat(dep);
    if (all.length < 1) {
      ctx.fillStyle = "#14110f";
      ctx.font = "700 20px sans-serif";
      ctx.textAlign = "left";
      ctx.fillText("Add fan points", padL, h / 2);
      return;
    }
    const maxP = Math.max(...all.map((p) => p.q));
    const maxQ = Math.max(...all.map((p) => p.p));
    const xNice = niceAxis(maxP, 5);
    const yNice = niceAxis(maxQ, 5);
    const xOf = (pa) => padL + (pa / xNice.max) * (w - padL - padR);
    const yOf = (flow) => padT + (1 - flow / yNice.max) * (h - padT - padB);
    ctx.strokeStyle = "#d7cbbd";
    ctx.lineWidth = 1;
    ctx.fillStyle = "#14110f";
    ctx.font = "700 15px sans-serif";
    ctx.textAlign = "center";
    for (let pa = 0; pa <= xNice.max + 1e-6; pa += xNice.step) {
      const x = xOf(pa);
      ctx.beginPath(); ctx.moveTo(x, padT); ctx.lineTo(x, h - padB); ctx.stroke();
      ctx.fillText(String(Math.round(pa)), x, h - padB + 22);
    }
    ctx.textAlign = "right";
    for (let flow = 0; flow <= yNice.max + 1e-6; flow += yNice.step) {
      const y = yOf(flow);
      ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(w - padR, y); ctx.stroke();
      ctx.fillText(String(Math.round(flow)), padL - 8, y + 5);
    }
    ctx.strokeStyle = "#14110f";
    ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(padL, padT); ctx.lineTo(padL, h - padB); ctx.lineTo(w - padR, h - padB); ctx.stroke();
    ctx.fillStyle = "#14110f";
    ctx.font = "800 16px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("Pressure (Pa)", (padL + w - padR) / 2, h - 16);
    ctx.save();
    ctx.translate(18, (padT + h - padB) / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText("Flow (L/s)", 0, 0);
    ctx.restore();
    function stroke(series, color) {
      if (series.length >= 2 && typeof monotoneSpline === "function") {
        const f = monotoneSpline(series);
        ctx.strokeStyle = color;
        ctx.lineWidth = 3;
        ctx.beginPath();
        const steps = 80;
        for (let i = 0; i <= steps; i++) {
          const pa = series[0].q + (series[series.length - 1].q - series[0].q) * i / steps;
          const flow = f(pa);
          const X = xOf(pa), Y = yOf(flow);
          if (i === 0) ctx.moveTo(X, Y); else ctx.lineTo(X, Y);
        }
        ctx.stroke();
      }
      series.forEach((pt) => {
        ctx.fillStyle = "#14110f";
        ctx.beginPath();
        ctx.arc(xOf(pt.q), yOf(pt.p), 5, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(xOf(pt.q), yOf(pt.p), 3, 0, Math.PI * 2);
        ctx.fill();
      });
    }
    stroke(press, "#d1243a");
    stroke(dep, "#1d4e89");
    ctx.font = "800 15px sans-serif";
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    let lx = padL;
    const ly = 22;
    function key(color, label) {
      ctx.fillStyle = color;
      ctx.fillRect(lx, ly - 6, 18, 12);
      ctx.fillStyle = "#14110f";
      ctx.fillText(label, lx + 24, ly);
      lx += ctx.measureText(label).width + 48;
    }
    key("#d1243a", "Pressurisation");
    if (depressOmitted === "yes") {
      ctx.fillStyle = "#6a5d50";
      ctx.fillText("Depressurisation omitted", lx, ly);
    } else key("#1d4e89", "Depressurisation");
    ctx.textBaseline = "alphabetic";
  }

  function drawFanLeak() {
    const press = fanSeries("pressPts");
    const dep = depressOmitted === "yes" ? [] : fanSeries("depPts");
    const small = document.getElementById("ftchart");
    if (small) drawFanOn(small.getContext("2d"), small.width, small.height, press, dep);
    const overlay = document.getElementById("ftOverlay");
    const big = document.getElementById("ftChartBig");
    if (overlay && big && !overlay.classList.contains("hidden")) {
      const dpr = Math.min(window.devicePixelRatio || 1, 2.5);
      const tw = Math.round(Math.max(280, big.clientWidth || window.innerWidth) * dpr);
      const th = Math.round(Math.max(220, big.clientHeight || window.innerHeight * 0.8) * dpr);
      if (big.width !== tw || big.height !== th) { big.width = tw; big.height = th; }
      drawFanOn(big.getContext("2d"), big.width, big.height, press, dep);
    }
  }

  function openFtChart() {
    const overlay = document.getElementById("ftOverlay");
    if (!overlay) return;
    overlay.classList.remove("hidden");
    document.documentElement.classList.add("overlay-open");
    drawFanLeak();
  }
  function closeFtChart() {
    const overlay = document.getElementById("ftOverlay");
    if (overlay) overlay.classList.add("hidden");
    document.documentElement.classList.remove("overlay-open");
  }

  function jobLabel() {
    const client = $("client").value.trim();
    const enclosure = $("enclosure").value.trim();
    if (client && enclosure) return client + " · " + enclosure;
    return client || enclosure || "";
  }
  function basisLabel() {
    if (minBasis === "extinguishing") return "Extinguishing concentration";
    if (minBasis === "eightyfive") return "85% of design concentration";
    return "1/1.3 × design concentration";
  }
  function reportDate() {
    const typed = $("testDate").value;
    const d = typed ? new Date(typed + "T00:00:00") : new Date();
    if (Number.isNaN(d.getTime())) return new Date().toLocaleDateString("en-AU", { day: "numeric", month: "long", year: "numeric" });
    return d.toLocaleDateString("en-AU", { day: "numeric", month: "long", year: "numeric" });
  }
  function reportFileName(site) {
    const job = (site || "room").replace(/[^a-zA-Z0-9-_]+/g, "_").replace(/^_+|_+$/g, "") || "room";
    return "FanTest-" + job + ".png";
  }
  function pointLines(title, points) {
    const rows = (points || []).filter((p) => p.p !== "" && p.q !== "" && p.p != null && p.q != null);
    if (!rows.length) return [title + ": none"];
    return [title].concat(rows.map((p) => "  " + p.p + " Pa    " + p.q + " L/s"));
  }
  function verLabel() {
    const el = document.getElementById("appBuild");
    return el && el.textContent ? el.textContent : "";
  }
  function reportPack() {
    const res = FanCalc.calculate(formInput());
    if (res.error) return null;
    const site = jobLabel();
    const ventIn = res.ventIn == null ? "Not required" : fmt(res.ventIn, 3) + " m²";
    const addOut = res.addOut === 0 ? "Nil" : fmt(res.addOut, 3) + " m²";
    const addIn = res.addIn == null ? "Not required" : (res.addIn === 0 ? "Nil" : fmt(res.addIn, 3) + " m²");
    const mix = res.mixing ? "Continuous mixing" : "Descending interface";
    const iso = res.iso2015 ? "ISO 14520-1:2015" : "ISO 14520-1:2006";
    const pass = res.pass ? "PASS" : "FAIL";
    const detail = "Predicted hold time " + fmt(res.holdMin, 2) + " min. The minimum retention for this test is " + res.holdLimit + " minutes.";
    const lines = [
      "Fan Test",
      "ROOM INTEGRITY",
      site || "Site / job not stated",
      reportDate(),
      "",
      pass,
      detail,
      "",
      "1. JOB",
      "Client: " + ($("client").value.trim() || "(not stated)"),
      "Enclosure: " + ($("enclosure").value.trim() || "(not stated)"),
      "Job number: " + ($("jobNo").value.trim() || "(not stated)"),
      "Tested by: " + ($("tester").value.trim() || "(not stated)"),
      "Test date: " + reportDate(),
      "",
      "2. AGENT AND ROOM",
      "Agent: " + res.agent.name,
      "Design concentration: " + fmt(res.design, 2) + " %",
      "Extinguishing concentration: " + fmt(res.extinguishing, 2) + " %",
      "Minimum concentration basis: " + basisLabel(),
      "Minimum concentration: " + fmt(res.cmin, 2) + " %",
      "Initial concentration: " + fmt(res.ci, 2) + " %",
      "Required agent mass: " + fmt(res.reqMass, 2) + " kg",
      "Installed agent mass: " + $("mass").value + " kg",
      "Room volume: " + $("volume").value + " m3",
      "Flooded height: " + $("floodedH").value + " m",
      "Minimum protected height: " + $("minHeight").value + " m",
      "Equivalent sharp interface: " + fmt(res.He, 2) + " m",
      "Inside / outside / design temperature: " + $("insideC").value + " / " + $("outsideC").value + " / " + $("designC").value + " °C",
      "Atmospheric pressure: " + $("atmBar").value + " bar",
      "Bias during test / hold: " + $("biasTest").value + " / " + $("biasHold").value + " Pa",
      "Air circulation: " + mix,
      "Pressure regulating: " + (pressureReg === "yes" ? "Yes" : "No"),
      "Lower leakage fraction: " + fmt(res.F * 100, 0) + " %",
      "",
      "3. FAN POINTS",
      ...pointLines("Pressurisation", readPoints("pressPts")),
      depressOmitted === "yes" ? "Depressurisation: omitted" : pointLines("Depressurisation", readPoints("depPts")).join("\n"),
      "",
      "4. LEAKAGE AND HOLD TIME",
      "Leakage exponent n: " + fmt(res.n, 3),
      "Correlation r, pressurisation: " + fmt(res.rPress, 3),
      "Correlation r, depressurisation: " + (res.rDep == null ? "omitted" : fmt(res.rDep, 3)),
      "Leakage constant k1: " + fmt(res.k1PerHour, 1) + " m3/h",
      "ELA at 10 Pa: " + fmt(res.elaCm2, 0) + " cm2",
      "Hold time: " + fmt(res.holdMin, 2) + " min",
      "Result: " + pass,
      "",
      "5. VENT ESTIMATE",
      "Maximum room strength: " + $("roomStrength").value + " Pa",
      "Discharge duration: " + $("dischargeS").value + " s",
      "Outward vent required: " + fmt(res.ventOut, 3) + " m2",
      "Additional outward vent: " + addOut,
      "Inward vent required: " + ventIn,
      "Additional inward vent: " + addIn,
      "",
      "6. STANDARDS",
      "ISO 14520-1 Annex E, door fan test for predicted minimum hold time. Interface height from " + iso + ".",
      "AS ISO 14520, the Australian adoption of ISO 14520, for gaseous fire-extinguishing enclosure integrity.",
      "AS 1851-2012, routine service of gaseous systems, including room integrity. Retention used here is " + res.holdLimit + " minutes.",
      "",
      "An A4 PNG of this report is attached. Print it fit-to-page.",
      "Field estimate only. Confirm the current Standards before sign-off."
    ];
    const body = lines.map((ln) => Array.isArray(ln) ? ln.join("\n") : ln).join("\n").replace(/\n{3,}/g, "\n\n");
    return {
      res: res,
      site: site,
      subject: "Room integrity " + pass + (site ? " — " + site : ""),
      body: body,
      fname: reportFileName(site || $("enclosure").value.trim() || "room"),
      png: drawReport({ res: res, site: site, detail: detail, ventIn: ventIn, addOut: addOut, addIn: addIn, mix: mix, iso: iso })
    };
  }
  function wrapText(ctx, text, maxW) {
    const words = String(text || "").split(/\s+/);
    const lines = [];
    let line = "";
    words.forEach((w) => {
      const t = line ? line + " " + w : w;
      if (ctx.measureText(t).width > maxW && line) { lines.push(line); line = w; }
      else line = t;
    });
    if (line) lines.push(line);
    return lines;
  }
  function fitText(ctx, text, maxW) {
    text = String(text || "");
    if (ctx.measureText(text).width <= maxW) return text;
    while (text.length > 1 && ctx.measureText(text + "…").width > maxW) text = text.slice(0, -1);
    return text + "…";
  }
  function drawReport(pack) {
    const w = 1654, h = 2339, m = 100, inner = w - 2 * m;
    const c = document.createElement("canvas");
    c.width = w; c.height = h;
    const ctx = c.getContext("2d");
    const res = pack.res;
    const ver = verLabel();
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = "#14110f";
    ctx.fillRect(0, 0, w, 128);
    ctx.fillStyle = "#d1243a";
    ctx.fillRect(0, 128, w, 6);
    ctx.fillStyle = "#d1243a";
    ctx.font = "800 22px sans-serif";
    ctx.fillText("FIRE PROTECTION", m, 48);
    ctx.fillStyle = "#e8b86d";
    ctx.font = "800 48px sans-serif";
    ctx.fillText("FAN TEST", m, 100);
    ctx.fillStyle = "#f4ede4";
    ctx.font = "800 22px sans-serif";
    ctx.textAlign = "right";
    ctx.fillText("ROOM INTEGRITY", w - m, 56);
    ctx.font = "700 18px sans-serif";
    ctx.fillStyle = "#a89b8c";
    if (ver) ctx.fillText(ver, w - m, 88);
    ctx.textAlign = "left";
    let y = 190;
    ctx.fillStyle = "#1a1613";
    ctx.font = "800 40px sans-serif";
    ctx.fillText("Enclosure integrity", m, y);
    y += 36;
    ctx.fillStyle = "#6a5d50";
    ctx.font = "600 20px sans-serif";
    ctx.fillText("Prepared " + reportDate() + (ver ? "  ·  FitterCalcs " + ver : "") + "  ·  A4", m, y);
    y += 34;
    if (pack.site) {
      ctx.fillStyle = "#d1243a";
      ctx.fillRect(m, y - 24, inner, 40);
      ctx.fillStyle = "#fff";
      ctx.font = "800 22px sans-serif";
      ctx.fillText(fitText(ctx, pack.site, inner - 28), m + 14, y + 4);
      y += 36;
    }
    y += 16;
    ctx.font = "700 20px sans-serif";
    const detailLines = wrapText(ctx, pack.detail, inner - 48).slice(0, 3);
    const boxH = 78 + detailLines.length * 26;
    ctx.fillStyle = res.pass ? "#0f6a3a" : "#d1243a";
    ctx.fillRect(m, y, inner, boxH);
    ctx.fillStyle = "#fff";
    ctx.font = "800 56px sans-serif";
    ctx.fillText(res.pass ? "PASS" : "FAIL", m + 22, y + 52);
    ctx.font = "700 20px sans-serif";
    let ty = y + 82;
    detailLines.forEach((ln) => { ctx.fillText(ln, m + 22, ty); ty += 26; });
    y += boxH + 36;
    const rows = [
      ["Agent", res.agent.name],
      ["Initial concentration", fmt(res.ci, 2) + " %"],
      ["Minimum concentration", fmt(res.cmin, 2) + " %  (" + basisLabel() + ")"],
      ["Required / installed mass", fmt(res.reqMass, 2) + " kg  /  " + $("mass").value + " kg"],
      ["Volume / flooded height", $("volume").value + " m³  /  " + $("floodedH").value + " m"],
      ["Equivalent interface", fmt(res.He, 2) + " m  ·  " + pack.iso],
      ["Leakage exponent n", fmt(res.n, 3)],
      ["Leakage constant k1", fmt(res.k1PerHour, 1) + " m³/h"],
      ["ELA at 10 Pa", fmt(res.elaCm2, 0) + " cm²"],
      ["Air circulation", pack.mix],
      ["Lower leakage fraction", fmt(res.F * 100, 0) + " %"],
      ["Outward vent", fmt(res.ventOut, 3) + " m², additional " + pack.addOut],
      ["Inward vent", pack.ventIn + ", additional " + pack.addIn]
    ];
    rows.forEach((r, i) => {
      const rowH = 46;
      if (i % 2 === 0) {
        ctx.fillStyle = "#efe6da";
        ctx.fillRect(m, y - 30, inner, rowH);
      }
      ctx.fillStyle = "#6a5d50";
      ctx.font = "600 18px sans-serif";
      ctx.textAlign = "left";
      ctx.fillText(r[0], m + 14, y);
      ctx.fillStyle = "#1a1613";
      ctx.font = "700 20px sans-serif";
      ctx.textAlign = "right";
      ctx.fillText(fitText(ctx, r[1], inner * 0.62), m + inner - 14, y);
      y += rowH;
    });
    ctx.textAlign = "left";
    y += 28;
    ctx.fillStyle = "#1a1613";
    ctx.font = "800 22px sans-serif";
    ctx.fillText("Standards", m, y);
    y += 32;
    ctx.font = "600 18px sans-serif";
    [
      "ISO 14520-1 Annex E, door fan test. Interface height from " + pack.iso + ".",
      "AS ISO 14520, Australian adoption of ISO 14520, gaseous enclosure integrity.",
      "AS 1851-2012, routine service. Retention used here is " + res.holdLimit + " minutes."
    ].forEach((ln) => {
      wrapText(ctx, ln, inner).forEach((line) => {
        ctx.fillStyle = "#1a1613";
        ctx.fillText(line, m, y);
        y += 26;
      });
      y += 6;
    });
    ctx.fillStyle = "#14110f";
    ctx.fillRect(0, h - 56, w, 56);
    ctx.fillStyle = "#d1243a";
    ctx.fillRect(0, h - 56, w, 4);
    ctx.fillStyle = "#fff";
    ctx.font = "600 18px sans-serif";
    ctx.textAlign = "left";
    ctx.fillText("A4  ·  print fit-to-page" + (ver ? "  ·  FitterCalcs " + ver : "") + "  ·  " + reportDate(), m, h - 22);
    ctx.textAlign = "right";
    ctx.fillText("Page 1 of 1", w - m, h - 22);
    return c.toDataURL("image/png");
  }
  function sendChartToApp(mode, dataUrl, fname, subject, body) {
    if (window.FitterCalcsPC) {
      if (mode === "email") OnlyFitters.emailPng(dataUrl, fname, subject, body);
      else OnlyFitters.savePng(dataUrl, fname);
      return;
    }
    const b64 = dataUrl.indexOf(",") >= 0 ? dataUrl.split(",")[1] : dataUrl;
    OnlyFitters.beginPng(mode, fname, subject || "", body || "");
    const CHUNK = 120000;
    for (let i = 0; i < b64.length; i += CHUNK) OnlyFitters.appendPng(b64.substring(i, i + CHUNK));
    OnlyFitters.finishPng();
  }
  function exportReport(mode) {
    const pack = reportPack();
    if (!pack) {
      const msg = "Enter the fan points and room figures before making a report";
      if (window.OnlyFitters && OnlyFitters.toast) OnlyFitters.toast(msg);
      else alert(msg);
      return;
    }
    if (window.OnlyFitters) {
      sendChartToApp(mode, pack.png, pack.fname, pack.subject, pack.body);
      return;
    }
    if (mode === "email") {
      location.href = "mailto:?subject=" + encodeURIComponent(pack.subject) + "&body=" + encodeURIComponent(pack.body);
      return;
    }
    const a = document.createElement("a");
    a.href = pack.png;
    a.download = pack.fname;
    a.click();
  }

  bindMenu("ftstdMenu", () => [
    { value: "2015", label: "ISO 14520-1:2015" },
    { value: "2006", label: "ISO 14520-1:2006" }
  ], () => standard, (v) => { standard = v; renderFan(); });
  bindMenu("ftmixMenu", () => [
    { value: "descending", label: "Descending interface" },
    { value: "continuous", label: "Continuous mixing" }
  ], () => mixing, (v) => { mixing = v; renderFan(); });
  bindMenu("ftagentMenu", () => FanCalc.AGENTS.map((a) => ({ value: a.name, label: a.name })), () => agentName, (v) => { agentName = v; renderFan(); });
  chipGroup("regChips", (v) => { pressureReg = v; });
  chipGroup("basisChips", (v) => { minBasis = v; });
  chipGroup("llfChips", (v) => { llfOverride = v; });
  chipGroup("omitChips", (v) => { depressOmitted = v; });
  document.querySelectorAll("#page-fantest input").forEach((el) => el.addEventListener("input", renderFan));
  pointTable("pressPts", FanCalc.SKY_AUS.pressPoints);
  pointTable("depPts", FanCalc.SKY_AUS.depressPoints);
  $("saveReport").onclick = () => exportReport("save");
  $("emailReport").onclick = () => exportReport("email");
  document.getElementById("ftchart").onclick = openFtChart;
  document.getElementById("ftchartOpen").onclick = openFtChart;
  document.getElementById("closeFtOverlay").onclick = closeFtChart;
  renderFan();
}
