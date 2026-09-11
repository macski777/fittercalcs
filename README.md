# FitterCalcs

Field calculator for fire protection fitters. Pipe sizes, Annubar flow, flanges, pump curves, hydro losses, tanks, and AS 1851 lookup — on your phone.

**Current version: 2.21**

[Download FitterCalcs.apk](https://github.com/macski777/fittercalcs/releases/latest)

## Install on Android

1. Download [FitterCalcs.apk](https://github.com/macski777/fittercalcs/releases/download/v2.21/FitterCalcs.apk).
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

## Font

- **App name and logo** use **Delta Corps Priest 1** (CoSMiC cHiLD / FIGlet). That is the stacked **FITTER / CALCS** wordmark and the **F / C** launcher icon.
- **Everything else** uses **JetBrains Mono**, the same typeface Omarchy uses (`omarchy font current`). Regular and Bold are bundled so phones match the Linux desktop.

## What’s in the app

| Tab | What it does |
| --- | --- |
| **Pipe** | OD, wall, ID for Sch 10 mill, SS 10S, Sch 40, SS 40S, Sch 5, CPVC. mm or inch. |
| **Annubar** | L/s from inHg for 3/8", 20T, and 21T. Type K to match the laminated card. |
| **Flange** | AS 2129 Table D/E/F/H, ANSI 150/300, PN16 — OD, PCD, bolts, holes. |
| **Pump** | kPa vs L/s curve, autosave by job name, save/email PNG, large-chart view. |
| **Hydro-Calcs** | Hazen-Williams friction + static rise. Steel C=120, stainless and CPVC C=150. |
| **Tanks** | Cylindrical / rectangular volume, effective kL. |
| **AS-1851** | Field lookup for AS 1851-2012 routine service. Not a substitute for the Standard. |

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
