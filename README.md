# FitterCalcs

<p align="center">
  <img src="docs/logo.png" width="112" alt="FitterCalcs FC logo">
  <br>
  <img src="docs/wordmark.svg" width="320" alt="FitterCalcs">
</p>

<p align="center">
  Field calculator for fire protection fitters.<br>
  AS 1074 pipe sizes, Annubar flow, flanges, pump curves, hydro losses, tanks with infill hours vs AS 2419.1 / AS 2118.1, and AS 1851 lookup.
</p>

<p align="center">
  <strong>Current version: 2.36</strong><br>
  <a href="https://github.com/macski777/fittercalcs/releases/latest">Download FitterCalcs.apk</a>
  ·
  <a href="https://github.com/macski777/fittercalcs/releases/latest">Windows</a>
  ·
  <a href="https://github.com/macski777/fittercalcs/releases/latest">Linux</a>
</p>

## Logo

The launcher icon and the **FITTER / CALCS** wordmark use **Delta Corps Priest 1** (CoSMiC cHiLD / FIGlet). Body text in the app is the original system sans font.

<p align="center">
  <img src="docs/logo.png" width="88" alt="FC logo">
  &nbsp;&nbsp;
  <img src="docs/wordmark.png" width="240" alt="FITTER CALCS wordmark">
</p>

## Install on Android

1. Download [FitterCalcs.apk](https://github.com/macski777/fittercalcs/releases/download/v2.36/FitterCalcs.apk).
2. Open the file on the phone.
3. Allow install from this source if Android asks.
4. Open **FitterCalcs**.

Needs Android 7 or newer.

## Install on Windows

1. Download [FitterCalcs-Setup.exe](https://github.com/macski777/fittercalcs/releases/download/v2.36/FitterCalcs-Setup.exe).
2. Double-click it. No admin, no wizard — it is a portable Windows app.
3. Pin it to the taskbar or copy it to the Desktop if you want it handy.

Needs 64-bit Windows 10 or 11.

## Install on Linux

1. Download [FitterCalcs-linux.tar.gz](https://github.com/macski777/fittercalcs/releases/download/v2.36/FitterCalcs-linux.tar.gz).
2. Unpack it and run `./install.sh` (installs for your user only).
3. Open **FitterCalcs** from the app menu, or run `fittercalcs`.

Needs Python 3, GTK 3, and WebKitGTK 4.1:

```bash
# Arch / Omarchy
sudo pacman -S python-gobject webkit2gtk-4.1

# Debian / Ubuntu
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1
```

## Updates

From **2.18** onward the app checks this repo when it opens.

- A red **Update** banner appears when a newer build is online.
- An Android notification is posted as well.
- Tap **Update** to download and install.
- Tap the version number (top right) to check by hand.

Phones on **2.17 or older** need a one-time install of 2.18 or later (USB or this page). After that they update themselves.

## What’s in the app

| Tab | What it does |
| --- | --- |
| **Pipe** | OD, wall, ID for AS 1074-1989 (R2018) Cl 2.3 Tables 2.1 / 2.2 / 2.3 Light / Medium / Heavy, SS 10S, SS 40S, CPVC. mm or inch. |
| **Annubar** | Type L/min or inHg for 3/8", 20T, and 21T. Table is 1–12 inHg; highlights the next inHg up. Medium-steel card K; other walls interpolate by ID. |
| **Flange** | AS 2129-2000 Tables D/E/F/H, ANSI 150/300, PN16 — OD, PCD, bolts, holes. |
| **Pump** | kPa vs L/s curve, autosave by job. Green **PASS** / red **FAIL** vs nominated duty. Email cites AS 2941-2013 Cl 10.3, AS 2419.1:2021 Cl 4.2.7.1.2, AS 2118.1:2017 Cl 14.9, AS 1851-2012 Table 3.4.3. |
| **Hydro-Calcs** | Hazen-Williams friction + static rise. Green **PASS** / red **FAIL** on typical 5 m/s (AS 2118.1-1999 Cl 12.14 is 10 m/s pipe / 6 m/s valves). Autosave by site / job. **Save to device** writes the A4 PNG. Email cites AS 1074 Cl 2.3, AS 2118.1:2017 Cl 14.10, AS 2419.1:2021 Cl 4.2.7.1.2. |
| **Tanks** | 1–4 tanks, combined effective kL. Hydrants 4 h (AS 2419.1:2021 Cl 4.2.1 / Cl 4.2.6.3). Sprinklers 30/60/90 min (AS 2118.1:2017 Cl 9.3 / Cl 10.3 / Sec 11). 20 mm overflow (AS/NZS 3500.1:2021 Cl 8.3.2). Autosave by site / job. **Save to device** writes the A4 PNG. |
| **AS-1851** | Field lookup for AS 1851-2012 routine service. Not a substitute for the Standard. |

### Pipe

AS 1074-1989 (R2018) Cl 2.3 Tables 2.1 / 2.2 / 2.3 Light, Medium, and Heavy steel, plus stainless and CPVC. Cross-section, OD / wall / ID, mm or inch.

<p align="center"><img src="docs/pipe.png" width="320" alt="Pipe tab — DN100 Medium"></p>

### Annubar

3/8", 20T, and 21T. Type **L/min** and the table (1–12 inHg) highlights the next listed **inHg** up (1.73 → 2). Type inHg to see the flow. 20T/21T K is from the medium steel card; other walls interpolate by ID.

<p align="center"><img src="docs/annubar.png" width="320" alt="Annubar tab — L/min to inHg"></p>

### Flange

AS 2129-2000 Tables D, E, F and H, ANSI, and PN16 — OD, PCD, bolts, hole size.

<p align="center"><img src="docs/flange.png" width="320" alt="Flange tab — DN100 Table D"></p>

### Pump

kPa vs L/s curve, job autosave, large chart. Enter a system duty and the tab shows green **PASS** or red **FAIL**. **Email report** is an A4 PNG plus a PASS/FAIL letter citing AS 2941-2013 Cl 10.3, AS 2419.1:2021 Cl 4.2.7.1.2, AS 2118.1:2017 Cl 14.9 and AS 1851-2012 Table 3.4.3.

<p align="center"><img src="docs/pump.png" width="320" alt="Pump tab — PASS against nominated duty"></p>

### Hydro-Calcs

Hazen-Williams friction plus static rise. Velocity within 5 m/s is green **PASS**; above is red **FAIL** (typical field limit — AS 2118.1-1999 Cl 12.14 allows 10 m/s in pipe, 6 m/s at valves). Calcs **autosave by site / job**. **Save to device** writes the A4 report PNG (same sheet as email). **Email report** cites AS 1074-1989 Cl 2.3 Tables 2.1–2.3, AS 2118.1:2017 Cl 14.10 and AS 2419.1:2021 Cl 4.2.7.1.2.

<p align="center"><img src="docs/hydro.png" width="320" alt="Hydro-Calcs tab — PASS on velocity"></p>

### Tanks

Pick **1 to 4 tanks**, each cylindrical or rectangular. Effective volumes add. Pick hydrants, sprinklers, or both; type infill / make-up. Hydrants **4 h** (AS 2419.1:2021 Cl 4.2.1 / Cl 4.2.6.3). Sprinklers **30 / 60 / 90 min** (AS 2118.1:2017 Cl 9.3 Light, Cl 10.3 Ordinary, Section 11 High Hazard). Combined systems: AS 2419.1:2021 Cl 4.2.3. Overflow default 20 mm: AS/NZS 3500.1:2021 Cl 8.3.2. Vortex / capacities: AS 2304:2019 Cl 7.3.5 / Cl 7.5. Enough storage is green **PASS**; short is red **FAIL**. Calcs **autosave by site / job**. **Save to device** writes the A4 report PNG.

<p align="center"><img src="docs/tanks.png" width="320" alt="Tanks tab — four tanks, combined storage vs hydrant duration"></p>

### Annubar K

- **20T** (single-mount 3/8″) and **21T** (dual-mount 3/8″) use the medium steel card: DN50 **0.638**, DN65 **0.617**, DN80 **0.665**, DN90 **0.661**, DN100 **0.672**, DN125 **0.671**, DN150 **0.706**.
- Light, Heavy, SS 10S, SS 40S (Sch 40 ID), and copper interpolate that K against mill ID. DN200+ holds the DN150 K.
- **3/8″** still uses the Diamond II formula. You can still type a K from another card. **Use probe K** puts the table/formula back.

## Field use

This is a site tool, not a certified hydraulic design or a replacement for mill cut sheets, probe charts, or the current Standard. Confirm before you cut, drill, or sign off a test.

## Publish a new version (maintainer)

Bump `versionName` / `versionCode` in `app/build.gradle` and `APP_VERSION` in the HTML, build the APK, then:

```bash
./publish-update.sh "Short note for the update banner"
```

That updates `update.json`, pushes `main`, and attaches `FitterCalcs.apk` to a GitHub release. Phones on 2.18+ pick it up next time they open the app.
