#!/usr/bin/env python3
"""
Resolve the compact seed into API-shaped planet records + SQL inserts.

Source of truth in git is planets.csv (274 diffable lines) + biomes.yaml.
Generated artefacts land in out/ and are never hand-edited.

    python3 build_seed.py [--verify path/to/live_planets.json]

--verify diffs the resolved output against a fresh pull of
helldiverstrainingmanual.com/api/v1/planets and exits non-zero on drift.
Wire that into CI as the patch-day canary.
"""

import argparse
import csv
import json
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).parent
SEED = ROOT / "seed"
OUT = ROOT / "out"

PLACEHOLDER_NAMES = {"", "Unknown"}


def load():
    biomes = yaml.safe_load((SEED / "biomes.yaml").read_text())
    hazards = yaml.safe_load((SEED / "hazards.yaml").read_text())
    overrides = yaml.safe_load((SEED / "planet_hazard_overrides.yaml").read_text())
    with (SEED / "planets.csv").open(encoding="utf-8") as fh:
        planets = list(csv.DictReader(fh))
    return biomes, hazards, overrides, planets


def resolve(biomes, hazards, overrides, planets):
    records, problems = [], []

    for row in planets:
        pid = int(row["id"])
        name = row["name"].strip()
        sector = row["sector"].strip() or None
        biome = row["biome"].strip() or None

        ov = overrides.get(pid)
        if ov and ov.get("is_override", True):
            haz, source = list(ov["actual"]), "override"
        elif biome:
            if biome not in biomes:
                problems.append(f"planet {pid} ({name}): unknown biome '{biome}'")
                haz, source = [], "biome"
            else:
                haz, source = list(biomes[biome].get("hazards") or []), "biome"
        else:
            haz, source = [], "biome"

        for h in haz:
            if h not in hazards:
                problems.append(f"planet {pid} ({name}): unknown hazard '{h}'")

        records.append({
            "id": pid,
            "name": name or None,
            "sector": sector,
            "biome": biome,
            "is_placeholder": name in PLACEHOLDER_NAMES,
            "hazards": haz,
            "hazard_source": source,
            "severity_load": sum(hazards[h]["severity"] for h in haz if h in hazards),
        })

    return records, problems


def sql_escape(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, int):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def emit_sql(records, biomes, hazards):
    lines = ["BEGIN;", ""]

    lines.append("-- biomes")
    for slug, b in biomes.items():
        lines.append(
            "INSERT INTO biomes (slug, display_name) VALUES "
            f"({sql_escape(slug)}, {sql_escape(b['display_name'])}) ON CONFLICT DO NOTHING;"
        )

    lines += ["", "-- hazards"]
    for slug, h in hazards.items():
        lines.append(
            "INSERT INTO hazards (slug, display_name, description, is_diurnal, severity) VALUES ("
            f"{sql_escape(slug)}, {sql_escape(h['display_name'])}, "
            f"{sql_escape(h.get('description'))}, {sql_escape(bool(h.get('is_diurnal')))}, "
            f"{h['severity']}) ON CONFLICT DO NOTHING;"
        )

    lines += ["", "-- hazard kit modifiers"]
    for slug, h in hazards.items():
        for tag, weight in (h.get("modifiers") or {}).items():
            lines.append(
                "INSERT INTO hazard_kit_modifiers (hazard_slug, tag, weight) VALUES "
                f"({sql_escape(slug)}, {sql_escape(tag)}, {weight}) ON CONFLICT DO NOTHING;"
            )

    lines += ["", "-- biome default hazards"]
    for slug, b in biomes.items():
        for h in (b.get("hazards") or []):
            lines.append(
                "INSERT INTO biome_hazards (biome_slug, hazard_slug) VALUES "
                f"({sql_escape(slug)}, {sql_escape(h)}) ON CONFLICT DO NOTHING;"
            )

    lines += ["", "-- planets"]
    for r in records:
        lines.append(
            "INSERT INTO planets_static (id, name, sector, biome_slug, is_placeholder) VALUES ("
            f"{r['id']}, {sql_escape(r['name'])}, {sql_escape(r['sector'])}, "
            f"{sql_escape(r['biome'])}, {sql_escape(r['is_placeholder'])}) "
            "ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name, sector=EXCLUDED.sector, "
            "biome_slug=EXCLUDED.biome_slug, is_placeholder=EXCLUDED.is_placeholder;"
        )
        for h in r["hazards"]:
            lines.append(
                "INSERT INTO planet_hazards (planet_id, hazard_slug, source) VALUES "
                f"({r['id']}, {sql_escape(h)}, {sql_escape(r['hazard_source'])}) "
                "ON CONFLICT DO NOTHING;"
            )

    lines += ["", "COMMIT;"]
    return "\n".join(lines) + "\n"


def verify(records, live_path):
    """Diff resolved output against a live /api/v1/planets pull."""
    live = json.loads(pathlib.Path(live_path).read_text())
    drift = []
    by_id = {r["id"]: r for r in records}

    for k, v in live.items():
        pid = int(k)
        got = {e["name"] for e in (v.get("environmentals") or [])}
        if pid not in by_id:
            drift.append(f"NEW PLANET INDEX {pid} ({v.get('name')!r}) — content signal")
            continue
        want_slugs = by_id[pid]["hazards"]
        want = {HAZARD_DISPLAY.get(s, s) for s in want_slugs}
        if got != want:
            drift.append(f"planet {pid} ({v.get('name')}): live={sorted(got)} seed={sorted(want)}")

    return drift


HAZARD_DISPLAY = {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", help="path to a fresh /api/v1/planets JSON dump")
    args = ap.parse_args()

    biomes, hazards, overrides, planets = load()
    HAZARD_DISPLAY.update({k: v["display_name"] for k, v in hazards.items()})

    records, problems = resolve(biomes, hazards, overrides, planets)

    OUT.mkdir(exist_ok=True)
    (OUT / "planets.json").write_text(json.dumps(records, indent=2, ensure_ascii=False))
    (OUT / "seed.sql").write_text(emit_sql(records, biomes, hazards))

    real = [r for r in records if not r["is_placeholder"]]
    print(f"resolved {len(records)} indices ({len(real)} named, "
          f"{len(records) - len(real)} placeholder)")
    print(f"overrides applied: {sum(1 for r in records if r['hazard_source'] == 'override')}")
    print(f"hazard-free planets: {sum(1 for r in real if not r['hazards'])}")
    print(f"wrote {OUT/'planets.json'} and {OUT/'seed.sql'}")

    for p in problems:
        print(f"  WARN {p}", file=sys.stderr)

    if args.verify:
        drift = verify(records, args.verify)
        if drift:
            print(f"\nDRIFT ({len(drift)}):", file=sys.stderr)
            for d in drift:
                print(f"  {d}", file=sys.stderr)
            sys.exit(1)
        print("verify: no drift")


if __name__ == "__main__":
    main()
