# RiverHome

**Know your stretch of river.** A calm, mobile-first companion that reads *your*
home stretch from live public data and tells you — plainly — what it's good for
today: swim, paddle, tube, or fish. Plus what's alive along the bank right now,
and how this week stacks up against normal.

> _Point it at your gauge. It reads the river._

The numbers and the safety calls don't depend on an LLM — they come from a
transparent rules engine running on real measurements, so RiverHome is a reliable
source with or without an API key.

## What it tells you

- **Right now** — live streamflow (with a rising/falling trend), gauge height,
  water temperature, and current weather, pulled straight from your gauge.
- **Flow, last 7 days** — a sparkline so you can see whether the river is on the
  rise, dropping, or holding.
- **Good for** — a go / caution / not-now call on **swimming, paddling,
  tubing/wading, and fishing**, each with a one-line reason. Computed from water
  temperature, flow (versus its recent range *or* your own flow bands), recent
  rain, wind, and storms.
- **Water-contact risk** — an honest estimate of bacterial risk from recent
  rainfall and runoff (the "wait 24–48h after heavy rain" rule), clearly labelled
  as an estimate rather than a measured sample.
- **Weather: normal · recent · ahead** — this week's climate normal (averaged
  over recent years), what actually fell in the last 7 days, and the 7-day
  forecast — historical vs realized vs predicted, side by side.
- **Life along the water** — species and flowering plants actually recorded near
  your stretch in the last 30 days (iNaturalist).
- **The read** *(with a Claude key)* — a short, grounded synthesis of the day and
  a seasonal ecology brief that names the real creatures and blooms nearby.

## Sources

Everything refreshes the moment you open the app — nothing about conditions is
cached or guessed:

| Layer | Source | Key needed |
|---|---|---|
| Flow, gauge height, water temp | [USGS Water Services](https://waterservices.usgs.gov/) | none |
| Weather, rainfall, forecast, climate history | [Open-Meteo](https://open-meteo.com/) (forecast + archive) | none |
| Active species & blooming plants | [iNaturalist](https://www.inaturalist.org/) | none |
| The daily read & ecology brief | Claude (Anthropic) | your own key |

The activity ratings and the contact-risk estimate are pure functions of the
measured data — auditable in `index.html`, no model in the loop. No key? You still
get every number, every rating, and the full ecology chips — just not the written
narrative. Your API key is entered on-device and sent only to Anthropic.

## Set it up

1. Open the app and tap **⚙︎**.
2. **Find your gauge.** Tap _📍 Find gauges near me_ to list active USGS stream
   gauges around your location and pick one — or enter a site number by hand from
   the [USGS Water Dashboard](https://dashboard.waterdata.usgs.gov/). Picking a
   gauge auto-fills the coordinates used for weather and ecology.
3. *(Optional but recommended)* set your river's **flow bands** — roughly what
   "normal" and "too high/pushy" look like at this gauge in cfs. Leave them blank
   and RiverHome judges flow against its own last 7 days.
4. *(Optional)* add an **Anthropic API key** for the written read and ecology
   brief. Stored only on your device.

## Run it locally

```bash
python3 -m http.server 8000   # then open http://localhost:8000
```

Self-contained PWA (`index.html` + `manifest.json` + `sw.js` + `icon.svg`) —
installable to a phone home screen; the app shell works offline.

## The one rule

Rivers change fast and every stretch is its own animal. RiverHome sharpens your
judgment — it doesn't replace it. Trust your eyes on the water, posted advisories,
and local knowledge first. **When in doubt, don't go in.**
