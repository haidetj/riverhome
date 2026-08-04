-- HD2 Kit Advisor — schema v0.1
-- Postgres 14+. Everything version-keyed to a SteamDB build id, not a semver,
-- because Arrowhead ships silent builds (e.g. 6.3.1 / build 24036910, Jul 7 2026).

BEGIN;

-- ---------------------------------------------------------------------------
-- VERSIONING
-- ---------------------------------------------------------------------------

CREATE TABLE patch_versions (
    build_id        BIGINT PRIMARY KEY,          -- SteamDB build id = master key
    semver          TEXT,                        -- '6.3.1' (may be null on silent builds)
    era_name        TEXT,                        -- 'Machinery of Oppression'
    released_at     TIMESTAMPTZ NOT NULL,
    notes_url       TEXT,
    notes_sha256    TEXT,                        -- content hash; recompute only on change
    has_balance_pass BOOLEAN NOT NULL DEFAULT FALSE,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- STATIC WORLD (seeded once, refreshed on patch)
-- ---------------------------------------------------------------------------

CREATE TABLE biomes (
    slug            TEXT PRIMARY KEY,
    display_name    TEXT NOT NULL,
    description     TEXT
);

CREATE TABLE hazards (
    slug            TEXT PRIMARY KEY,
    display_name    TEXT NOT NULL,              -- exact API string, used for matching
    description     TEXT,
    is_diurnal      BOOLEAN NOT NULL DEFAULT FALSE,  -- Durial/Nocturnal variants
    severity        SMALLINT NOT NULL DEFAULT 1       -- 1 minor .. 3 kit-defining
);

-- Default hazard set implied by a biome. True for ~97% of planets.
CREATE TABLE biome_hazards (
    biome_slug      TEXT NOT NULL REFERENCES biomes(slug),
    hazard_slug     TEXT NOT NULL REFERENCES hazards(slug),
    PRIMARY KEY (biome_slug, hazard_slug)
);

CREATE TABLE planets_static (
    id              INTEGER PRIMARY KEY,         -- planetIndex, 0..273 as of build 24036910
    name            TEXT,                        -- NULL/'' for unreleased placeholders
    sector          TEXT,                        -- NULL for the unreleased tail (267+)
    biome_slug      TEXT REFERENCES biomes(slug),
    is_placeholder  BOOLEAN NOT NULL DEFAULT FALSE,  -- empty name or 'Unknown'
    first_seen_build BIGINT REFERENCES patch_versions(build_id),
    aliases         TEXT[] NOT NULL DEFAULT '{}'
);

-- Resolved per-planet hazards. Populated from biome_hazards, then overridden.
-- source='biome'   -> inherited
-- source='override'-> planet contradicts its biome (6 known cases; see seed)
CREATE TABLE planet_hazards (
    planet_id       INTEGER NOT NULL REFERENCES planets_static(id) ON DELETE CASCADE,
    hazard_slug     TEXT NOT NULL REFERENCES hazards(slug),
    source          TEXT NOT NULL CHECK (source IN ('biome','override')),
    PRIMARY KEY (planet_id, hazard_slug)
);

CREATE INDEX planets_static_name_trgm ON planets_static USING gin (name gin_trgm_ops);
-- requires: CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ---------------------------------------------------------------------------
-- LIVE WAR STATE (polled)
-- ---------------------------------------------------------------------------

CREATE TABLE planets_live (
    planet_id       INTEGER NOT NULL REFERENCES planets_static(id),
    snapshot_at     TIMESTAMPTZ NOT NULL,
    faction         TEXT NOT NULL,               -- owner: Terminids|Automatons|Illuminates|Super Earth
    players         INTEGER NOT NULL,
    health          BIGINT,
    max_health      BIGINT,
    liberation_pct  NUMERIC(7,4),
    is_defense      BOOLEAN NOT NULL DEFAULT FALSE,
    expires_at      TIMESTAMPTZ,                 -- defense campaigns only; NULL on liberations
    is_mo_target    BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (planet_id, snapshot_at)
);

CREATE INDEX planets_live_recent ON planets_live (snapshot_at DESC);

CREATE TABLE major_orders (
    id              BIGINT PRIMARY KEY,
    title           TEXT,
    briefing        TEXT,
    expires_at      TIMESTAMPTZ,
    target_planets  INTEGER[] NOT NULL DEFAULT '{}',
    raw             JSONB,
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- MISSION CATALOG (static; API does not expose per-planet mission pools)
-- ---------------------------------------------------------------------------

CREATE TABLE missions (
    id              TEXT PRIMARY KEY,
    display_name    TEXT NOT NULL,
    archetype       TEXT NOT NULL CHECK (archetype IN
                      ('eradicate','blitz','eliminate','objective','evac','sabotage','survey')),
    factions        TEXT[] NOT NULL,
    campaign_types  TEXT[] NOT NULL DEFAULT '{liberation,defense}',
    difficulty_min  SMALLINT NOT NULL DEFAULT 1,
    difficulty_max  SMALLINT NOT NULL DEFAULT 10,
    duration_band   TEXT CHECK (duration_band IN ('short','standard','long')),
    tags            TEXT[] NOT NULL DEFAULT '{}',
    verified        BOOLEAN NOT NULL DEFAULT FALSE   -- pending wiki.gg cross-check
);

-- ---------------------------------------------------------------------------
-- ITEM CATALOG + META GRADES
-- ---------------------------------------------------------------------------

CREATE TABLE items (
    id              TEXT PRIMARY KEY,            -- 'plas_101_purifier'
    display_name    TEXT NOT NULL,
    slot            TEXT NOT NULL CHECK (slot IN
                      ('primary','secondary','throwable','support','backpack',
                       'stratagem','armor','booster')),
    weapon_type     TEXT,                        -- 'Energy-Based','Shotgun','Marksman Rifle'
    source          TEXT,                        -- warbond / 'Superstore' / 'Campaign Reward'
    dps             NUMERIC(10,2),
    armor_pen       SMALLINT,                    -- 2=Light 3=Medium 4=Heavy
    tags            TEXT[] NOT NULL DEFAULT '{}',
    patch_added     BIGINT REFERENCES patch_versions(build_id),
    provisional     BOOLEAN NOT NULL DEFAULT FALSE,  -- <5 days of signal
    aliases         TEXT[] NOT NULL DEFAULT '{}'     -- 'AC','RR','500kg','Quasar'
);

-- One row per (item, faction, source). NOT telemetry — editorial grading.
CREATE TABLE item_grades (
    item_id         TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    faction         TEXT NOT NULL CHECK (faction IN ('terminids','automatons','illuminate')),
    grade           TEXT NOT NULL CHECK (grade IN ('S+','S','A','B','C','D')),
    grader          TEXT NOT NULL,               -- 'ugg','gamesradar','manual'
    build_id        BIGINT REFERENCES patch_versions(build_id),
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (item_id, faction, grader)
);

-- Materialised agreement: promote to S only on >=2 concurring graders.
-- Full-tier disagreement drops to A and lands here for human review.
CREATE TABLE meta_conflicts (
    id              BIGSERIAL PRIMARY KEY,
    item_id         TEXT NOT NULL REFERENCES items(id),
    faction         TEXT NOT NULL,
    grades          JSONB NOT NULL,              -- {"ugg":"S+","gamesradar":"B"}
    resolved_grade  TEXT,
    status          TEXT NOT NULL DEFAULT 'open'
                      CHECK (status IN ('open','resolved','wontfix')),
    opened_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    note            TEXT
);

-- Patch-note deltas. Feeds a decay penalty on recently nerfed items.
CREATE TABLE balance_events (
    id              BIGSERIAL PRIMARY KEY,
    build_id        BIGINT NOT NULL REFERENCES patch_versions(build_id),
    item_id         TEXT REFERENCES items(id),
    direction       TEXT NOT NULL CHECK (direction IN ('buff','nerf','rework','neutral')),
    field           TEXT,                        -- 'damage','spread','magazine'
    old_value       TEXT,
    new_value       TEXT,
    raw_line        TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- KIT RULES
-- ---------------------------------------------------------------------------

-- Hazard -> additive tag weights. Never a hard replace.
CREATE TABLE hazard_kit_modifiers (
    hazard_slug     TEXT NOT NULL REFERENCES hazards(slug),
    tag             TEXT NOT NULL,
    weight          NUMERIC(4,2) NOT NULL,       -- negative = discourage
    rationale       TEXT,
    PRIMARY KEY (hazard_slug, tag)
);

CREATE TABLE kit_templates (
    id              TEXT PRIMARY KEY,
    faction         TEXT NOT NULL,
    archetype       TEXT NOT NULL,
    build_min       BIGINT REFERENCES patch_versions(build_id),
    slots           JSONB NOT NULL,
    score           NUMERIC(4,3),
    status          TEXT NOT NULL DEFAULT 'active'
                      CHECK (status IN ('active','provisional','deprecated')),
    sources         TEXT[] NOT NULL DEFAULT '{}',
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- OPS
-- ---------------------------------------------------------------------------

CREATE TABLE ingest_runs (
    id              BIGSERIAL PRIMARY KEY,
    source          TEXT NOT NULL,
    ok              BOOLEAN NOT NULL,
    payload_sha256  TEXT,                        -- skip downstream work if unchanged
    changed         BOOLEAN NOT NULL DEFAULT FALSE,
    docs_n          INTEGER,
    error           TEXT,
    ran_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- New planet indices appearing = unreleased content leak. Alert on insert.
CREATE TABLE content_signals (
    id              BIGSERIAL PRIMARY KEY,
    kind            TEXT NOT NULL,               -- 'new_planet_index','new_biome_slug'
    detail          JSONB NOT NULL,
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMIT;
