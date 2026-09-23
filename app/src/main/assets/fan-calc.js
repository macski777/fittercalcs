/* Door-fan enclosure integrity, ported from the FireVac sheet
   "Sky Aus UPS Room 01.xlsx" (Fan Test Input + Math + Halocarbon Agents).
   Leakage fit and hold time follow that sheet's ISO 14520-1 Annex E equations. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.FanCalc = factory();
})(typeof self !== "undefined" ? self : this, function () {
  var AGENTS = [
    { name: "IG-55 Proinert", density: 1.41, Ip: 0.63, It: 1.3, design: 43.7, extinguishing: 33.6, k1: 0.6598, k2: 0.002416, kind: "I" },
    { name: "IG-55 Argonite or LPG", density: 1.41, Ip: 0.63, It: 1.3, design: 45.1, extinguishing: 34.675, k1: 0.6598, k2: 0.002416, kind: "I" },
    { name: "HFC-227ea FM-200", density: 7.26, Ip: 0.68, It: 0.8, design: 8.5, extinguishing: 6.555, k1: 0.1269, k2: 0.000513, kind: "H" },
    { name: "IG-541 Inergen to ISO 2006", density: 1.4169, Ip: 0.63, It: 1.3, design: 39.9, extinguishing: 30.115, k1: 0.65799, k2: 0.00239, kind: "I" },
    { name: "IG-541 Inergen to ISO 2015", density: 1.4169, Ip: 0.63, It: 1.3, design: 41.7, extinguishing: 30.115, k1: 0.65799, k2: 0.00239, kind: "I" },
    { name: "IG-541 Proinert2 to ISO 2006", density: 1.4169, Ip: 0.63, It: 1.3, design: 39.9, extinguishing: 30.115, k1: 0.65799, k2: 0.00239, kind: "I" },
    { name: "IG-541 Proinert2 to ISO 2015", density: 1.4169, Ip: 0.63, It: 1.3, design: 41.7, extinguishing: 30.115, k1: 0.65799, k2: 0.00239, kind: "I" },
    { name: "FK-5-1-12 Novec 1230", density: 13.66, Ip: 0.52, It: 0.45, design: 5.6, extinguishing: 4.27, k1: 0.0664, k2: 0.000274, kind: "H" }
  ];

  var PA = 1.205;
  var G = 9.81;
  var PC = 1.013;
  var TC = 20;
  var HOLD_MIN = 10;

  function num(v) {
    var n = typeof v === "number" ? v : parseFloat(v);
    return Number.isFinite(n) ? n : NaN;
  }

  function agentByName(name) {
    for (var i = 0; i < AGENTS.length; i++) if (AGENTS[i].name === name) return AGENTS[i];
    return null;
  }

  function linreg(xs, ys) {
    var n = xs.length;
    var sx = 0, sy = 0, sxx = 0, sxy = 0;
    for (var i = 0; i < n; i++) {
      sx += xs[i];
      sy += ys[i];
      sxx += xs[i] * xs[i];
      sxy += xs[i] * ys[i];
    }
    var den = n * sxx - sx * sx;
    var slope = (n * sxy - sx * sy) / den;
    var intercept = (sy - slope * sx) / n;
    var ybar = sy / n;
    var ssTot = 0, ssRes = 0;
    for (var j = 0; j < n; j++) {
      var pred = slope * xs[j] + intercept;
      ssTot += (ys[j] - ybar) * (ys[j] - ybar);
      ssRes += (ys[j] - pred) * (ys[j] - pred);
    }
    return { n: slope, intercept: intercept, r2: ssTot > 0 ? 1 - ssRes / ssTot : 1 };
  }

  function fitDirection(points, pbt, depress) {
    var xs = [], ys = [];
    (points || []).forEach(function (pt) {
      var p = num(pt.p), q = num(pt.q);
      if (!Number.isFinite(p) || !Number.isFinite(q) || q <= 0) return;
      var corrected = depress ? -Math.abs(p) - pbt : Math.abs(p) - pbt;
      if (!(Math.abs(corrected) > 0)) return;
      xs.push(Math.log(Math.abs(corrected)));
      ys.push(Math.log(Math.abs(q / 1000)));
    });
    if (xs.length < 2) return null;
    return linreg(xs, ys);
  }

  function halocarbonVents(name, conc, volume, pMax, seconds) {
    var safety = 1.2, eff = 1, rh = 0.38;
    var psf = 0.02088543 * pMax;
    var humidIn = 1.69 - 1.79 * rh;
    var humidOut = 0.81 + 0.51 * rh;
    var lvrn, lvrp;
    if (name.indexOf("FM-200") >= 0 || name.indexOf("227") >= 0) {
      lvrn = (34.81 * (conc / 0.0625) * (10 / seconds) * Math.exp(-0.1063 * psf)) * humidIn;
      lvrp = ((conc / 0.0625) * (10 / seconds) * 35.7 * Math.exp(-0.238 * psf)) * humidOut;
    } else {
      lvrn = ((conc / 0.042) * (10 / seconds) * 43.02 * Math.exp(-0.08333 * psf)) * humidIn;
      lvrp = ((conc / 0.042) * (10 / seconds) * 40.43 * Math.exp(-0.613 * psf)) * humidOut;
    }
    var scale = safety * ((volume * 35.31467) / 1000) * 0.00064516 / eff;
    return { inward: scale * lvrn, outward: scale * lvrp };
  }

  function simpsonMinutes(pmf, pmi, c) {
    var steps = 20;
    var xs = [];
    for (var i = 0; i <= steps; i++) xs.push(pmf + (pmi - pmf) * i / steps);
    function y(x) {
      var top = 2 * c.g * c.H0 * Math.pow(x - c.pa, (c.n + 1) / c.n) + 2 * c.Pbh * Math.pow(x - c.pa, 1 / c.n);
      var bot = x + c.pa * Math.pow(c.F / (1 - c.F), 1 / c.n);
      return Math.pow(top / bot, -c.n);
    }
    var ys = xs.map(y);
    if (ys.some(function (v) { return !Number.isFinite(v); })) return NaN;
    var acc = 0;
    for (var k = 0; k < steps; k += 2) acc += ys[k] + 4 * ys[k + 1] + ys[k + 2];
    var integral = acc * (pmi - pmf) / (3 * steps);
    return ((c.V / (c.F * c.k2)) * integral) / 60;
  }

  function calculate(inp) {
    var agent = agentByName(inp.agent);
    if (!agent) return { error: "Pick an agent" };
    var Te = num(inp.insideC), To = num(inp.outsideC), Td = num(inp.designC);
    var Pbt = num(inp.biasTest), Pbh = num(inp.biasHold), Pt = num(inp.atmBar);
    var H0 = num(inp.floodedH), V = num(inp.volume), Hp = num(inp.minHeight);
    var mass = num(inp.mass), Pmax = num(inp.roomStrength), discharge = num(inp.dischargeS);
    if (![Te, To, Td, Pbt, Pbh, Pt, H0, V, Hp, mass, Pmax, discharge].every(Number.isFinite)) {
      return { error: "Enter the room, agent and bias figures" };
    }
    if (!(V > 0) || !(H0 > 0) || !(discharge > 0) || !(Pt > 0)) return { error: "Volume, flooded height, discharge time and atmospheric pressure must be above zero" };

    var iso2015 = inp.standard !== "2006";
    var mixing = inp.mixing === "continuous";
    var depressOmitted = inp.depressOmitted === true || inp.depressOmitted === "yes";
    var pressureReg = !(inp.pressureReg === false || inp.pressureReg === "no");
    var llfOverride = inp.llfOverride === true || inp.llfOverride === "yes";
    var F = llfOverride ? num(inp.llfPct) / 100 : 0.5;
    if (!(F > 0) || !(F < 1)) return { error: "Lower leakage fraction must be between 0 and 100%" };

    var S = agent.k1 + agent.k2 * Td;
    var ci = 100 - (100 / Math.exp(S * mass / V));
    var cmin = inp.minBasis === "extinguishing" ? agent.extinguishing
      : inp.minBasis === "over13" ? agent.design / 1.3
      : 0.85 * agent.design;
    var reqMass = V / S * Math.log(100 / (100 - agent.design));

    var press = fitDirection(inp.pressPoints, Pbt, false);
    if (!press) return { error: "Need at least two pressurisation points with room pressure above the test bias" };
    var depress = null;
    if (!depressOmitted) {
      depress = fitDirection(inp.depressPoints, Pbt, true);
      if (!depress) return { error: "Need at least two depressurisation points, or mark depressurisation omitted" };
    }

    var B42 = Math.sqrt((PC * (To + 273)) / (Pt * (TC + 273)));
    var C42 = Math.sqrt((PC * (Te + 273)) / (Pt * (TC + 273)));
    var B43 = (Te + 273) / (To + 273);
    var C43 = (To + 273) / (Te + 273);
    var nP = press.n;
    var k1P = Math.exp(press.intercept) * B42 * B43 * Math.pow((Pt * 293) / (1.013 * (Te + 273)), nP);
    var nD = null, k1D = null;
    if (depress) {
      nD = depress.n;
      k1D = Math.exp(depress.intercept) * C42 * C43 * Math.pow((Pt * 293) / (1.013 * (To + 273)), nD);
    }

    var pe = agent.density;
    var pmi = pe * (ci / 100) + PA * ((100 - ci) / 100);
    var pmf = pe * (cmin / 100) + PA * ((100 - cmin) / 100);
    var Pmi = G * H0 * Math.abs(pmi - PA);

    var Ip = agent.Ip, It = agent.It;
    var heA = Hp + It * (cmin / ci - Ip);
    var heB = H0 - (H0 - Hp) * Ip * ci / cmin;
    var he2015 = heA >= (H0 - Ip * It) ? heB : heA;
    var he2006 = cmin < 0.5 * ci ? Hp : H0 - (H0 - Hp) * (ci / (2 * cmin));
    var He = iso2015 ? he2015 : he2006;

    var n, k1;
    if (depressOmitted) {
      n = nP;
      k1 = k1P;
    } else {
      var qP = k1P * Math.pow(Math.abs(Pmi), nP);
      var qD = k1D * Math.pow(Math.abs(Pmi), nD);
      var qPh = k1P * Math.pow(Math.abs(0.5 * Pmi), nP);
      var qDh = k1D * Math.pow(Math.abs(0.5 * Pmi), nD);
      var qAvg = (qP + qD) / 2;
      var qAvgH = (qPh + qDh) / 2;
      n = (Math.log(qAvg) - Math.log(qAvgH)) / Math.log(2);
      k1 = Math.exp((Math.log(qAvgH) * Math.log(Pmi) - Math.log(qAvg) * (Math.log(Pmi) - Math.log(2))) / Math.log(2));
    }

    var k2 = k1 * Math.pow(PA / 2, n);
    var fRatio = Math.pow(F / (1 - F), 1 / n);
    var k3 = (2 * G * Math.abs(pmi - PA)) / (pmi + PA * fRatio);
    var k4 = (2 * Pbh) / (pmi + PA * Math.pow(F / 1 - F, 1 / n));
    var holdDesc = ((V / H0) * (Math.pow(k3 * H0 + k4, 1 - n) - Math.pow(k3 * He + k4, 1 - n)) / ((1 - n) * k2 * F * k3)) / 60;
    var holdMix = simpsonMinutes(pmf, pmi, { g: G, H0: H0, Pbh: Pbh, pa: PA, F: F, n: n, V: V, k2: k2 });
    var holdMin = mixing ? holdMix : holdDesc;

    var q10 = k1 * Math.pow(10, n);
    var elaCm2 = (q10 * Math.sqrt(PA / 20) / 0.61) * 10000;

    var proinert = /proinert/i.test(agent.name);
    var massFlow = (proinert || pressureReg) ? mass / discharge : (mass / discharge) * 2.7;
    var inertVent = massFlow * (1 / pe) / Math.sqrt(Pmax * (1 / pmi));
    var ventOut, ventIn;
    if (agent.kind === "H") {
      var hv = halocarbonVents(agent.name, ci / 100, V, Pmax, discharge);
      ventOut = hv.outward;
      ventIn = hv.inward;
    } else {
      ventOut = inertVent;
      ventIn = null;
    }
    var elaM2 = elaCm2 / 10000;
    function extra(req) {
      if (req == null) return null;
      return (req - elaM2) < 0 ? 0 : req - elaM2;
    }

    var column = mixing ? G * H0 * Math.abs(pmf - PA) : G * He * Math.abs(pmi - PA);
    var biasOk = !(Pbh < 0 && column < Math.abs(Pbh));

    return {
      error: null,
      agent: agent,
      ci: ci,
      cmin: cmin,
      design: agent.design,
      extinguishing: agent.extinguishing,
      reqMass: reqMass,
      He: He,
      n: n,
      k1: k1,
      k1PerHour: k1 * 3600,
      rPress: Math.sqrt(Math.max(0, press.r2)),
      rDep: depress ? Math.sqrt(Math.max(0, depress.r2)) : null,
      elaCm2: elaCm2,
      holdMin: holdMin,
      holdDesc: holdDesc,
      holdMix: holdMix,
      pass: Number.isFinite(holdMin) && holdMin >= HOLD_MIN,
      holdLimit: HOLD_MIN,
      ventOut: ventOut,
      ventIn: ventIn,
      addOut: extra(ventOut),
      addIn: extra(ventIn),
      biasOk: biasOk,
      mixing: mixing,
      iso2015: iso2015,
      F: F
    };
  }

  return {
    AGENTS: AGENTS,
    HOLD_MIN: HOLD_MIN,
    calculate: calculate,
    SKY_AUS: {
      agent: "IG-541 Proinert2 to ISO 2015",
      standard: "2015",
      insideC: 20,
      outsideC: 20,
      designC: 20,
      biasTest: 2,
      biasHold: 2,
      atmBar: 1.013,
      mixing: "descending",
      floodedH: 3.96,
      volume: 126.56,
      minHeight: 2,
      mass: 66.5,
      minBasis: "over13",
      llfOverride: false,
      llfPct: 15,
      depressOmitted: false,
      pressureReg: true,
      roomStrength: 500,
      dischargeS: 9,
      pressPoints: [
        { p: 10, q: 550 }, { p: 20, q: 740 }, { p: 30, q: 860 }, { p: 40, q: 990 }, { p: 50, q: 1110 }
      ],
      depressPoints: [
        { p: 10, q: 130 }, { p: 20, q: 308 }, { p: 30, q: 425 }, { p: 40, q: 530 }, { p: 50, q: 610 }
      ]
    }
  };
});
