# HD2 Kit Advisor — data foundation

Cold-start seed for the planet/mission/kit advisor. Everything here is derived from
a live pull of `helldiverstrainingmanual.com/api/v1/planets` on 2026-08-02, against
build 24036910 (patch 6.3.1, *Machinery of Oppression* era).

```
schema.sql                          Postgres DDL, build-id versioned
seed/planets.csv                    274 indices — id, name, sector, biome (source of truth)
seed/biomes.yaml                    24 biomes -> default hazard sets
seed/hazards.yaml                   14 hazards -> kit tag modifiers (closed set)
seed/planet_hazard_overrides.yaml   5 planets that contradict their biome
seed/missions.yaml                  mission archetype scaffold (UNVERIFIED)
build_seed.py                       resolves the above -> out/
out/planets.json                    API-shaped resolved records
out/seed.sql                        idempotent inserts

sourcing/refresh.py                 the sourcing workflow — static seed + live war state -> web/data/
sourcing/htm.py                     read-only client for the HTM community API
sourcing/fixtures/                  sample live payloads for offline runs / tests
web/index.html                      the display — Front / Planets / Advisor, no build step
web/data/                           generated JSON the display reads (refreshed by the workflow)
.github/workflows/sourcing.yml      cron + manual "update now" -> refresh + commit-on-change
.github/workflows/pages.yml         publish web/ to GitHub Pages
```

Load the database (optional — the display does not need Postgres):

```bash
psql -f schema.sql
python3 build_seed.py
psql -f out/seed.sql
```

Run the display locally:

```bash
pip install pyyaml
python3 sourcing/refresh.py --offline sourcing/fixtures   # or drop --offline for a live pull
python3 -m http.server -d web 8000                         # open http://localhost:8000
```

Or bake a single self-contained file you can open with no server (data inlined):

```bash
python3 sourcing/build_preview.py   # -> web/preview.html  (regenerate after each refresh)
```

---

## The two live pieces

**The display (`web/`).** A single self-contained page — no framework, no build.
Three views:

- **Front** — active campaigns ranked by urgency (MO target › defense-with-a-clock ›
  most-contested liberation), a Major Order banner with a countdown, and per-planet
  kit hints. This is the "where should I drop and what should I bring" screen.
- **Planets** — search / filter all 269 named worlds by name, sector, biome or hazard;
  the detail pane shows each environmental (severity, description, day/night flag),
  override flags, and a diverging bar chart of the kit tags the hazards favour vs punish.
- **Advisor** — pick a planet (+ optional faction / mission) and get the favoured and
  discouraged kit tags, with the Ion-Storm and day/night callouts spelled out. Weights
  are the additive tag modifiers from `hazards.yaml`, summed across the planet's
  environmentals — hover any bar for the per-hazard breakdown.

The page reads only the JSON in `web/data/`, so it deploys to any static host.

**The sourcing workflow (`sourcing/refresh.py` + Actions).** One command does the
whole ingestion path:

- resolves the git seed into `web/data/planets.json` + `rules.json` (static; changes on patch),
- pulls live war state from the HTM API into `web/data/live.json` + `major_orders.json`
  (active campaigns, defense timers, MO targets, ranked by urgency),
- runs the **canary** (the seed-vs-live diff) and records any drift in `meta.json`,
- degrades gracefully — if HTM is down it still rewrites the static half and logs the failure.

`.github/workflows/sourcing.yml` runs it every 6 hours **and** on a manual
`workflow_dispatch` (an "update now" button, with a `strict` toggle that fails the run
on canary drift for patch-day checks). It commits `web/data/` only when the payload
actually changed. `pages.yml` republishes the display on every such commit, so the live
site tracks the latest pull.

---

## What the data actually says

**Hazards are static, not weather.** They are a fixed property of the planet, not a
live condition. This kills the "poll `/planets` every 6–24hr" job in the original
framework — it's a seed refreshed on patch, verified by canary.

**The hazard set is closed: 14 values.** Distribution across 269 named planets:

| Hazard | Planets | | Hazard | Planets |
|--|--|--|--|--|
| Extreme Cold | 52 | | Blizzards | 21 |
| Rainstorms | 47 | | Nocturnal Extreme Cold | 18 |
| Thick Fog | 40 | | Sandstorms | 18 |
| **Ion Storms** | **34** | | Acid Storms | 15 |
| Intense Heat | 31 | | Fire Tornadoes | 15 |
| Durial Intense Heat | 30 | | Meteor Storms | 14 |
| Tremors | 28 | | Volcanic Activity | 22 |

Ion Storms is the headline. 34 planets — 13% of the galaxy — intermittently disable
stratagems. That's the single largest kit-shaping variable in the dataset, and it
inverts the usual advice: orbitals and Eagles get punished, support weapons and a
strong primary get rewarded. Weighted at ±0.8 in `hazards.yaml`, the highest in the file.

40 named planets have **zero** hazards (ethereal, tundra, shattered, magma). Those are
the pure faction-and-archetype cases with no environmental modifier at all.

**Mesa planets carry a day/night pair.** Durial Intense Heat *and* Nocturnal Extreme
Cold on the same world — energy weapons swing from penalised to favoured depending on
the clock. Heze Bay (182), currently an active campaign, is one of 18.

**HTM's docs are wrong about exceptions.** They claim environmentals always follow
biome with Tien Kwan as the sole exception. There are five real contradictions, and
Tien Kwan is not among them — it carries its own `icemoss-special` slug and resolves
cleanly. The actual outliers are Ivis (51), Maw (63), Genesis Prime (95),
Achernar Secundus (130), Matar Bay (200). Genesis Prime is a full *substitution* —
jungle biome, but Ion Storms instead of Volcanic Activity + Rainstorms.

Undergrowth is a single-sample biome (Gacrux, 171), so its "default" is unverified.
Flagged in the overrides file.

**Free content-leak detector.** Indices 263–265 are unnamed, 270–271 are `Unknown`,
267 "Big Rock" has no sector, and 272/273 (Basquine VIII, Sangis) carry the `autumn`
slug — the Forest (Fall) biome 6.3.0 shipped. New indices appearing in the planets
payload is a leading indicator of unreleased content. `build_seed.py --verify` catches
it and `content_signals` records it.

---

## The canary

```bash
curl -s https://helldiverstrainingmanual.com/api/v1/planets > /tmp/live.json
python3 build_seed.py --verify /tmp/live.json   # exits 1 on drift
```

Run daily. It fails on three things worth knowing about: a new planet index, a hazard
array that changed under an existing planet, and a new biome slug. All three mean
Arrowhead shipped something.

---

## Design notes carried into the schema

**Build id, not semver, is the version key.** 6.3.1 shipped Jul 7 as build 24036910
with no published weapon retunes. Silent builds happen and the Zendesk notes lag.
Everything foreign-keys to `patch_versions.build_id`.

**`item_grades` is editorial, not telemetry.** There is no public HD2 pick-rate data —
u.gg's HD2 tier list is small-team testing, unlike its LoL/TFT boards which aggregate
real matches. The schema stores one row per (item, faction, **grader**) precisely so
you can require two concurring sources before promoting to S, and route full-tier
disagreements to `meta_conflicts` for a human. Don't build a regression on top of this;
the data doesn't support one.

**`planets_live` keeps `is_defense` and `expires_at`.** The original framework's
normalised record dropped both. They're the urgency signal — a defense campaign at 6%
with a ticking clock should outrank a stalled liberation with three times the players.

---

## Not done yet

The display and the sourcing loop are built (above). What's still open:

1. **No items yet.** The u.gg parser is the next build — four pages
   (primary/secondary/support/throwables), static HTML tables, deterministic parse,
   no LLM needed. That populates `items` + `item_grades` in one pass, and gives the
   Advisor concrete weapons to name instead of kit *tags*. `sourcing/refresh.py` is the
   place to hang it — add an `items` source next to the war-state pull.
2. **`missions.yaml` is unverified.** Every entry is `verified: false`. The shape is
   right; the names and difficulty gates need a wiki.gg pass. The Advisor already
   surfaces the `verified: false` warning so the scaffold can't masquerade as truth.
3. **No patch-note delta hook.** Wants to exist before **Aug 12**, when
   Castellan's Creed lands: 4 new items (R/40-K Hot-Shot, P/40-K Bolt Pistol,
   40-K Meltagun, G/40-K Meltamine), 2 armour sets with the True Grit passive, and
   almost certainly a balance patch alongside. That's the natural first live test of
   the whole ingestion path — provisional-flag the new items, watch the grades settle.
   The canary already fires on new planet indices / biome slugs; a patch-note diff is
   the item-side equivalent.
