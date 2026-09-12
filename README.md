# FitterCalcs

<p align="center">
  <img src="docs/logo.png" width="112" alt="FitterCalcs FC logo">
  <br>
  <img src="docs/wordmark.svg" width="320" alt="FitterCalcs">
</p>

<p align="center">
  Field calculator for fire protection fitters.<br>
  AS 1074 pipe sizes, Annubar flow, flanges, pump curves, hydro losses, tanks, and AS 1851 lookup.
</p>

<p align="center">
  <strong>Current version: 2.23</strong><br>
  <a href="https://github.com/macski777/fittercalcs/releases/latest">Download FitterCalcs.apk</a>
</p>

## Logo

The launcher icon and the **FITTER / CALCS** wordmark use **Delta Corps Priest 1** (CoSMiC cHiLD / FIGlet). Body text in the app is the original system sans font.

<p align="center">
  <img src="docs/logo.png" width="88" alt="FC logo">
  &nbsp;&nbsp;
  <img src="docs/wordmark.png" width="240" alt="FITTER CALCS wordmark">
</p>

## Install on Android

1. Download [FitterCalcs.apk](https://github.com/macski777/fittercalcs/releases/download/v2.23/FitterCalcs.apk).
2. Open the file on the phone.
3. Allow install from this source if Android asks.
4. Open **FitterCalcs**.

Needs Android 7 or newer.

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
| **Pipe** | OD, wall, ID for AS 1074 Light / Medium / Heavy, SS 10S, SS 40S, CPVC. mm or inch. |
| **Annubar** | L/s from inHg for 3/8", 20T, and 21T. Type K to match the laminated card. |
| **Flange** | AS 2129 Table D/E/F/H, ANSI 150/300, PN16 — OD, PCD, bolts, holes. |
| **Pump** | kPa vs L/s curve, autosave by job name, save/email PNG, large-chart view. |
| **Hydro-Calcs** | Hazen-Williams friction + static rise. Steel C=120, stainless and CPVC C=150. |
| **Tanks** | Cylindrical / rectangular volume, effective kL. |
| **AS-1851** | Field lookup for AS 1851-2012 routine service. Not a substitute for the Standard. |

### Pipe

AS 1074 Light, Medium, and Heavy steel, plus stainless and CPVC. Cross-section, OD / wall / ID, mm or inch.

<p align="center"><img src="docs/pipe.png" width="320" alt="Pipe tab — DN100 Medium"></p>

### Annubar

3/8", 20T, and 21T. Type a K from the probe card, or use the formula K.

<p align="center"><img src="docs/annubar.png" width="320" alt="Annubar tab — DN50 Medium"></p>

### Flange

AS 2129 tables, ANSI, and PN16 — OD, PCD, bolts, hole size.

<p align="center"><img src="docs/flange.png" width="320" alt="Flange tab — DN100 Table D"></p>

### Pump

kPa vs L/s curve, job autosave, save/email PNG, large chart.

<p align="center"><img src="docs/pump.png" width="320" alt="Pump tab — test curve"></p>

### Hydro-Calcs

Hazen-Williams friction plus static rise.

<p align="center"><img src="docs/hydro.png" width="320" alt="Hydro-Calcs tab"></p>

### Annubar K

- **20T** is **0.637** at Sch 40 DN50. Other sizes and walls use the blockage formula on mill ID.
- **21T** is **0.672** at Sch 40 DN100, same math.
- You can still type a K from the probe card. **Use probe K** puts the formula back.

## Field use

This is a site tool, not a certified hydraulic design or a replacement for mill cut sheets, probe charts, or the current Standard. Confirm before you cut, drill, or sign off a test.

## Publish a new version (maintainer)

Bump `versionName` / `versionCode` in `app/build.gradle` and `APP_VERSION` in the HTML, build the APK, then:

```bash
./publish-update.sh "Short note for the update banner"
```

That updates `update.json`, pushes `main`, and attaches `FitterCalcs.apk` to a GitHub release. Phones on 2.18+ pick it up next time they open the app.
