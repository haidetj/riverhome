#!/usr/bin/env python3
"""
Sourcing workflow — keep the advisor's data fresh.

One command does the whole ingestion path:

    python3 sourcing/refresh.py                 # live pull, write web/data/*
    python3 sourcing/refresh.py --strict        # exit 1 on canary drift (CI / patch-day)
    python3 sourcing/refresh.py --offline DIR   # read fixtures from DIR, no network

What it produces under web/data/ (everything the display reads):

    planets.json        resolved static records (from the git seed, source of truth)
    rules.json          hazards + biomes + missions + kit-tag glossary (from seed)
    live.json           normalised live war state (active campaigns, ranked)
    major_orders.json   current Major Order(s), normalised
    meta.json           generated_at, source hashes, canary drift, per-source status

The static half (planets.json, rules.json) is derived from the seed and changes
only on patch. The live half (live.json, major_orders.json) is what the cron job
refreshes. meta.json records whether anything actually changed so the workflow can
skip an empty commit.

Design: the live half degrades gracefully. If HTM is down, we still rewrite the
static half and record the failure in meta.json rather than crashing the job.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from datetime import datetime, timezone

# --- make the repo-root seed builder importable -----------------------------
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import build_seed  # noqa: E402  (resolve/load/verify live here)
import yaml  # noqa: E402

try:
    from sourcing import htm  # when run as `python -m sourcing.refresh`
except ImportError:  # when run as a script
    import htm  # type: ignore

WEB_DATA = ROOT / "web" / "data"
SEED = ROOT / "seed"

FACTIONS = {
    "Terminids": "terminids",
    "Automaton": "automatons",
    "Automatons": "automatons",
    "Illuminate": "illuminate",
    "Illuminates": "illuminate",
    "Humans": "super_earth",
    "Super Earth": "super_earth",
}


def now_iso() -> str:
    """UTC timestamp; overridable via SOURCE_NOW for deterministic fixtures/tests."""
    override = os.environ.get("SOURCE_NOW")
    if override:
        return override
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ---------------------------------------------------------------------------
# STATIC HALF — resolve the seed into client-shaped JSON
# ---------------------------------------------------------------------------

def build_static():
    biomes, hazards, overrides, planets = build_seed.load()
    records, problems = build_seed.resolve(biomes, hazards, overrides, planets)
    missions = yaml.safe_load((SEED / "missions.yaml").read_text()) or []

    rules = {
        "hazards": {
            slug: {
                "display_name": h["display_name"],
                "description": h.get("description"),
                "severity": h.get("severity", 1),
                "is_diurnal": bool(h.get("is_diurnal")),
                "modifiers": h.get("modifiers") or {},
            }
            for slug, h in hazards.items()
        },
        "biomes": {
            slug: {
                "display_name": b["display_name"],
                "hazards": b.get("hazards") or [],
                "note": b.get("note"),
                "status": b.get("status"),
            }
            for slug, b in biomes.items()
        },
        "missions": missions,
        "tag_glossary": TAG_GLOSSARY,
    }
    return records, rules, problems, hazards


def display_to_slug(hazards: dict) -> dict:
    return {h["display_name"]: slug for slug, h in hazards.items()}


# ---------------------------------------------------------------------------
# LIVE HALF — normalise the war state
# ---------------------------------------------------------------------------

def _faction(v):
    if v is None:
        return None
    return FACTIONS.get(str(v), str(v).lower())


def _num(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return default


def _epoch_to_iso(v):
    """HTM hands defense expiry as epoch seconds (sometimes ms). Best-effort ISO."""
    if v in (None, "", 0):
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    if n > 1e12:  # milliseconds
        n /= 1000.0
    try:
        return datetime.fromtimestamp(n, tz=timezone.utc).replace(microsecond=0).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def extract_mo_planet_ids(mo_payload) -> set:
    """Best-effort: pull planet indices a Major Order targets.

    MO shapes vary. We scan the common ones (setting.tasks[].values with a
    planet-index task type, and any explicit target arrays) and stay
    conservative — a missed target just means a campaign card won't get the MO
    ribbon, which is cosmetic.
    """
    ids: set = set()
    orders = mo_payload if isinstance(mo_payload, list) else [mo_payload]
    for order in orders:
        if not isinstance(order, dict):
            continue
        setting = order.get("setting") or order
        for task in (setting.get("tasks") or []):
            if not isinstance(task, dict):
                continue
            vals = task.get("values") or []
            vtypes = task.get("valueTypes") or []
            # valueType 12 == "planet index" in the HTM/ArrowHead task schema
            for vt, val in zip(vtypes, vals):
                if vt == 12:
                    ids.add(_num(val))
            # some payloads expose planetIndex directly
            if "planetIndex" in task:
                ids.add(_num(task["planetIndex"]))
        for key in ("planetIndex", "targetPlanets", "targets"):
            v = order.get(key)
            if isinstance(v, int):
                ids.add(v)
            elif isinstance(v, list):
                ids.update(_num(x) for x in v if isinstance(x, (int, float, str)))
    return {i for i in ids if i >= 0}


def normalise_major_orders(mo_payload):
    orders = mo_payload if isinstance(mo_payload, list) else [mo_payload]
    out = []
    for order in orders:
        if not isinstance(order, dict):
            continue
        setting = order.get("setting") or {}
        out.append({
            "id": order.get("id32") or order.get("id"),
            "title": setting.get("overrideTitle") or order.get("title"),
            "briefing": setting.get("overrideBrief") or order.get("briefing"),
            "description": setting.get("taskDescription") or order.get("description"),
            "expires_at": _epoch_to_iso(order.get("expiresIn") and None) or _epoch_to_iso(order.get("expiresAt")),
            "expires_in_s": _num(order.get("expiresIn"), None) if order.get("expiresIn") is not None else None,
            "target_planets": sorted(extract_mo_planet_ids(order)),
        })
    return out


def normalise_live(planets_payload, campaign_payload, status_payload, mo_payload,
                   static_records, hazards):
    """Fold the live endpoints into a compact, ranked campaign list."""
    disp2slug = display_to_slug(hazards)
    static_by_id = {r["id"]: r for r in static_records}
    mo_ids = extract_mo_planet_ids(mo_payload) if mo_payload is not None else set()

    # per-planet live enrichment from /v1/planets (keyed by index)
    planets = planets_payload or {}

    def planet_state(pid):
        return planets.get(str(pid)) or planets.get(pid) or {}

    # defense-event expiry keyed by planet index (from /v1/war/status planetEvents)
    expiry_by_id = {}
    if isinstance(status_payload, dict):
        for ev in (status_payload.get("planetEvents") or []):
            if not isinstance(ev, dict):
                continue
            pid = _num(ev.get("planetIndex"), -1)
            if pid >= 0 and ev.get("expireTime"):
                expiry_by_id[pid] = ev.get("expireTime")

    # the active set comes from /v1/war/campaign; fall back to planets with players
    campaigns_raw = campaign_payload if isinstance(campaign_payload, list) else []
    if not campaigns_raw and planets:
        campaigns_raw = [
            {"planetIndex": _num(k)} for k, v in planets.items()
            if _num((v or {}).get("players")) > 0 and _num(k) != 0
        ]

    campaigns = []
    total_players = 0
    faction_players: dict = {}
    for c in campaigns_raw:
        if not isinstance(c, dict):
            continue
        pid = _num(c.get("planetIndex", c.get("index", c.get("id"))), -1)
        if pid < 0:
            continue
        st = planet_state(pid)
        static = static_by_id.get(pid, {})

        players = _num(c.get("players", st.get("players")))
        owner = _faction(c.get("faction") or c.get("owner") or st.get("owner"))
        is_defense = bool(c.get("defense") or c.get("type") == 1 or pid in expiry_by_id)
        liberation = c.get("percentage", st.get("percentage"))
        try:
            liberation = round(float(liberation), 3) if liberation is not None else None
        except (TypeError, ValueError):
            liberation = None

        # hazards: trust the static seed (authoritative); cross-check live env names
        hazards_slugs = list(static.get("hazards") or [])
        if not hazards_slugs:
            live_env = {(e or {}).get("name") for e in (st.get("environmentals") or [])}
            hazards_slugs = [disp2slug[n] for n in live_env if n in disp2slug]

        expires = _epoch_to_iso(c.get("expireDateTime") or c.get("endTime")
                                or expiry_by_id.get(pid))

        campaigns.append({
            "id": pid,
            "name": c.get("name") or st.get("name") or static.get("name"),
            "sector": st.get("sector") or static.get("sector"),
            "biome": (st.get("biome") or {}).get("slug") if isinstance(st.get("biome"), dict) else static.get("biome"),
            "owner": owner,
            "players": players,
            "health": _num(c.get("health", st.get("health")), None),
            "max_health": _num(c.get("maxHealth", st.get("maxHealth")), None),
            "liberation": liberation,
            "is_defense": is_defense,
            "expires_at": expires,
            "is_mo_target": pid in mo_ids,
            "hazards": hazards_slugs,
            "severity_load": static.get("severity_load", 0),
        })
        total_players += players
        if owner:
            faction_players[owner] = faction_players.get(owner, 0) + players

    campaigns.sort(key=_urgency, reverse=True)

    return {
        "campaigns": campaigns,
        "summary": {
            "active_campaigns": len(campaigns),
            "defenses": sum(1 for c in campaigns if c["is_defense"]),
            "mo_targets": sum(1 for c in campaigns if c["is_mo_target"]),
            "total_players": total_players,
            "faction_players": faction_players,
        },
    }


def _urgency(c):
    """Rank campaigns: MO defense with a ticking clock first, stalled liberations last."""
    score = 0.0
    if c["is_mo_target"]:
        score += 1000
    if c["is_defense"]:
        score += 500
        if c["expires_at"]:
            score += 250  # a real countdown outranks an open-ended defense
    # closeness to the wire adds urgency for defenses, contest adds it for liberations
    lib = c.get("liberation")
    if lib is not None:
        score += (100 - abs(50 - lib))  # most-contested (near 50%) float up
    score += min(c.get("players", 0), 60000) / 1000.0
    return score


# ---------------------------------------------------------------------------
# ORCHESTRATION
# ---------------------------------------------------------------------------

def load_fixture(dirpath: pathlib.Path, name: str):
    p = dirpath / f"{name}.json"
    if not p.exists():
        return None, None
    payload = json.loads(p.read_text())
    return payload, htm.sha256(payload)


def write_json(path: pathlib.Path, obj) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, indent=2, ensure_ascii=False) + "\n"
    path.write_text(text)
    return htm.sha256(obj)


def main():
    ap = argparse.ArgumentParser(description="Refresh advisor data (static seed + live war state).")
    ap.add_argument("--offline", metavar="DIR",
                    help="read planets/campaign/status/major_orders fixtures from DIR instead of the network")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 if the seed canary detects drift against live /planets")
    ap.add_argument("--no-live", action="store_true",
                    help="rewrite only the static half (planets.json, rules.json)")
    args = ap.parse_args()

    meta = {"generated_at": now_iso(), "sources": {}, "ok": True, "changed": False}

    # ---- static half (always) --------------------------------------------
    records, rules, problems, hazards = build_static()
    rules["generated_at"] = meta["generated_at"]
    write_json(WEB_DATA / "planets.json", records)
    write_json(WEB_DATA / "rules.json", rules)
    for p in problems:
        print(f"  WARN {p}", file=sys.stderr)
    print(f"static: {len(records)} planet indices, {len(rules['hazards'])} hazards, "
          f"{len(rules['biomes'])} biomes, {len(rules['missions'])} missions")

    if args.no_live:
        write_json(WEB_DATA / "meta.json", meta)
        return 0

    # ---- fetch live -------------------------------------------------------
    payloads = {}
    for name in ("planets", "campaign", "status", "major_orders"):
        try:
            if args.offline:
                payload, sha = load_fixture(pathlib.Path(args.offline), name)
                if payload is None:
                    raise FileNotFoundError(f"{name}.json missing in {args.offline}")
            else:
                payload, sha = htm.fetch_named(name)
            payloads[name] = payload
            meta["sources"][name] = {"ok": True, "sha256": sha}
        except Exception as exc:  # noqa: BLE001 — degrade, don't crash the job
            payloads[name] = None
            meta["sources"][name] = {"ok": False, "error": str(exc)}
            meta["ok"] = False
            print(f"  WARN source {name} failed: {exc}", file=sys.stderr)

    # ---- normalise + write live ------------------------------------------
    if payloads.get("planets") is not None or payloads.get("campaign") is not None:
        live = normalise_live(payloads.get("planets"), payloads.get("campaign"),
                              payloads.get("status"), payloads.get("major_orders"),
                              records, hazards)
        live["generated_at"] = meta["generated_at"]
        write_json(WEB_DATA / "live.json", live)
        mos = normalise_major_orders(payloads.get("major_orders") or [])
        write_json(WEB_DATA / "major_orders.json",
                   {"generated_at": meta["generated_at"], "orders": mos})
        meta["summary"] = live["summary"]
        print(f"live: {live['summary']['active_campaigns']} campaigns "
              f"({live['summary']['defenses']} defense, {live['summary']['mo_targets']} MO), "
              f"{len(mos)} major order(s)")
    else:
        print("  WARN no live planet data — leaving previous live.json in place", file=sys.stderr)

    # ---- canary: does the seed still match live /planets? -----------------
    drift = []
    if payloads.get("planets") is not None:
        build_seed.HAZARD_DISPLAY.update({k: v["display_name"] for k, v in hazards.items()})
        tmp = WEB_DATA / ".live_planets.tmp.json"
        tmp.write_text(json.dumps(payloads["planets"]))
        try:
            drift = build_seed.verify(records, str(tmp))
        finally:
            tmp.unlink(missing_ok=True)
    meta["canary"] = {"checked": payloads.get("planets") is not None,
                      "drift_count": len(drift), "drift": drift[:50]}
    if drift:
        print(f"\nCANARY DRIFT ({len(drift)}):", file=sys.stderr)
        for d in drift:
            print(f"  {d}", file=sys.stderr)

    write_json(WEB_DATA / "meta.json", meta)

    if args.strict and drift:
        return 1
    return 0


TAG_GLOSSARY = {
    "energy": "Energy / laser weapons",
    "high_rof_ballistic": "High rate-of-fire ballistics",
    "sustain_fire": "Sustained-fire weapons",
    "light_armor": "Light armor",
    "stamina_booster": "Stamina Booster",
    "ammo_independent": "Ammo-independent weapons",
    "orbital": "Orbital stratagems",
    "eagle": "Eagle stratagems",
    "support_weapon": "Support weapons",
    "strong_primary": "A strong standalone primary",
    "sentry": "Sentry / emplacement stratagems",
    "backpack_sustain": "Sustain backpacks (ammo/supply)",
    "fire_kit": "Fire-based weapons",
    "fire_resist_armor": "Fire-resistant armor",
    "mobility": "Mobility (light kit, jump pack)",
    "static_position": "Holding a static position",
    "shield_pack": "Shield backpack",
    "ranged": "Ranged engagement",
    "close_quarters": "Close-quarters engagement",
    "melee": "Melee",
    "stagger_primary": "Stagger primaries",
    "close_range": "Close-range weapons",
    "marksman": "Marksman / long-range",
    "guard_dog": "Guard Dog / Rover",
    "radar_booster": "Radar booster",
    "jump_pack": "Jump pack",
    "light_pen": "Light armor-penetration",
    "heavy_pen": "Heavy armor-penetration",
}


if __name__ == "__main__":
    raise SystemExit(main())
