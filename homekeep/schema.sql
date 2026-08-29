-- Homekeep — the home ledger.
--
-- `docs/03_data_model.md` expressed as DDL. One sentence, from that doc: a home is
-- a tree of spaces and items; everything else is either something that happened to
-- them, something to do about them, or a paper trail — and every write arrives as
-- a Proposal.
--
-- Flavour: SQLite, so v0 can run on a phone or a single file. Postgres notes are
-- inline where the two differ; the shape is deliberately the same either way, and
-- open question #3 is answered here — relational + embeddings + a generic Link
-- table, not a graph DB.
--
-- The MVP app (`index.html`) implements the subset marked [MVP] below and keeps it
-- in IndexedDB with these exact field names, so the ledger can move to SQL without
-- a migration of meaning.

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- Provenance
--
-- Rule 1: every record carries provenance. These three columns repeat on every
-- table below rather than living in a side table — a row is not interpretable
-- without them, and a join that can be forgotten will be.
--
--   source_observation_id  the capture this record came from; NULL if typed
--                          straight into a form by the owner
--   stated_by              'owner' | 'agent' | 'research'
--   confidence             0.0–1.0. Owner-stated facts are 1.0 and outrank
--                          agent-inferred ones on conflict.
--
-- Rule 2: uncertain values store the value AND its certainty, in a sibling
-- `*_certainty` column: 'stated' | 'estimated_from_photo' | 'inferred' | 'unknown'.
-- `installed: 2014, installed_certainty: 'estimated_from_photo'` is what tells the
-- agent this is worth asking about later.
-- ---------------------------------------------------------------------------

-- [MVP] The vault root. One per household.
CREATE TABLE home (
  id            TEXT PRIMARY KEY,
  address       TEXT,
  year_built    INTEGER,
  year_built_certainty TEXT DEFAULT 'unknown',
  type          TEXT,                      -- house | condo | townhouse | other
  ownership     TEXT,                      -- owned | rented | managed
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);

-- [MVP] Room or zone: kitchen, attic, north exterior. The spatial backbone.
CREATE TABLE space (
  id            TEXT PRIMARY KEY,
  home_id       TEXT NOT NULL REFERENCES home(id) ON DELETE CASCADE,
  name          TEXT NOT NULL,
  kind          TEXT,                      -- room | exterior | system | outbuilding | land
  floor         TEXT,
  notes         TEXT,
  source_observation_id TEXT REFERENCES observation(id),
  stated_by     TEXT NOT NULL DEFAULT 'owner',
  confidence    REAL NOT NULL DEFAULT 1.0,
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);
CREATE INDEX space_home_idx ON space(home_id);

-- [MVP] Any thing: appliance, system, fixture, material, structural component.
-- Items nest (HVAC → compressor) via parent_id.
CREATE TABLE item (
  id            TEXT PRIMARY KEY,
  space_id      TEXT REFERENCES space(id) ON DELETE SET NULL,
  parent_id     TEXT REFERENCES item(id) ON DELETE SET NULL,
  name          TEXT NOT NULL,
  category      TEXT,                      -- appliance | system | fixture | material | structural
  brand         TEXT,
  model         TEXT,
  serial        TEXT,
  installed     TEXT,                      -- ISO date or bare year; free-form on purpose
  installed_certainty TEXT DEFAULT 'unknown',
  condition     TEXT,                      -- good | fair | poor | failing | unknown
  expected_life_years INTEGER,
  status        TEXT NOT NULL DEFAULT 'active',   -- active | removed | replaced
  notes         TEXT,
  source_observation_id TEXT REFERENCES observation(id),
  stated_by     TEXT NOT NULL DEFAULT 'owner',
  confidence    REAL NOT NULL DEFAULT 1.0,
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);
CREATE INDEX item_space_idx  ON item(space_id);
CREATE INDEX item_parent_idx ON item(parent_id);

-- [MVP] A raw capture: photo, voice transcript, or typed note, plus what the agent
-- extracted from it. Rule 3: observations ALWAYS save, before any extraction runs
-- and whether or not it succeeds. Never deleted except by a full vault wipe — this
-- is the provenance every other row points at.
--
-- Rule 6: photos are kept (media_ref), because they are the record — before/after,
-- condition evidence, insurance proof. Voice audio is transcribed and discarded;
-- only `transcript` survives.
CREATE TABLE observation (
  id            TEXT PRIMARY KEY,
  home_id       TEXT NOT NULL REFERENCES home(id) ON DELETE CASCADE,
  kind          TEXT NOT NULL,             -- photo | voice | text
  media_ref     TEXT,                      -- photo only; NULL once voice audio is discarded
  transcript    TEXT,                      -- voice transcript, or the typed note
  caption       TEXT,                      -- what the owner said alongside a photo
  extracted     TEXT,                      -- JSON: what the agent read out of it
  extract_status TEXT NOT NULL DEFAULT 'pending',  -- pending | done | failed | skipped
  extract_error TEXT,
  captured_at   TEXT NOT NULL
);
CREATE INDEX observation_home_idx ON observation(home_id, captured_at DESC);

-- [MVP] The card. A proposed change to any entity, from an observation or a
-- research finding. Rule 3: nothing but an observation lands without one.
--
-- `change` is a full proposed field set for the target row, not a JSON patch
-- (v0 decision — see docs/README.md). `op` is 'create' or 'update'; target_id is
-- NULL for a create.
--
-- Rule 4: dismissed proposals are KEPT, never deleted. `signature` is what makes
-- that rule enforceable — a stable hash of (target_type, target_id, field, value).
-- The agent does not re-propose a change whose signature already sits dismissed;
-- a different value is new evidence and may be proposed again.
CREATE TABLE proposal (
  id            TEXT PRIMARY KEY,
  home_id       TEXT NOT NULL REFERENCES home(id) ON DELETE CASCADE,
  source_type   TEXT NOT NULL,             -- observation | research | owner
  source_id     TEXT,
  target_type   TEXT NOT NULL,             -- space | item | issue | task | ...
  target_id     TEXT,
  op            TEXT NOT NULL,             -- create | update
  title         TEXT NOT NULL,             -- what the card says on its face
  rationale     TEXT,                      -- why the agent thinks so, in one line
  change        TEXT NOT NULL,             -- JSON: proposed fields
  signature     TEXT NOT NULL,
  confidence    REAL NOT NULL DEFAULT 0.5,
  status        TEXT NOT NULL DEFAULT 'pending',  -- pending | accepted | edited | dismissed
  applied_id    TEXT,                      -- the row this became, once accepted
  decided_at    TEXT,
  created_at    TEXT NOT NULL
);
CREATE INDEX proposal_pending_idx   ON proposal(home_id, status, created_at DESC);
CREATE INDEX proposal_signature_idx ON proposal(home_id, signature, status);

-- Phase 2. A problem on an item or space.
CREATE TABLE issue (
  id            TEXT PRIMARY KEY,
  home_id       TEXT NOT NULL REFERENCES home(id) ON DELETE CASCADE,
  item_id       TEXT REFERENCES item(id) ON DELETE SET NULL,
  space_id      TEXT REFERENCES space(id) ON DELETE SET NULL,
  title         TEXT NOT NULL,
  severity      TEXT,                      -- watch | soon | urgent
  status        TEXT NOT NULL DEFAULT 'open',     -- open | watching | resolved
  first_seen    TEXT,
  resolved_at   TEXT,
  resolution    TEXT,
  source_observation_id TEXT REFERENCES observation(id),
  stated_by     TEXT NOT NULL DEFAULT 'owner',
  confidence    REAL NOT NULL DEFAULT 1.0,
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);

-- Phase 2. Scoped work. Can start from an Issue or from nothing.
CREATE TABLE project (
  id            TEXT PRIMARY KEY,
  home_id       TEXT NOT NULL REFERENCES home(id) ON DELETE CASCADE,
  issue_id      TEXT REFERENCES issue(id) ON DELETE SET NULL,
  title         TEXT NOT NULL,
  scope         TEXT,
  status        TEXT NOT NULL DEFAULT 'idea',     -- idea | scoped | quoted | in_progress | done
  budget        REAL,
  started_at    TEXT,
  finished_at   TEXT,
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);

-- [MVP, manual only] One actionable, optionally recurring. Reminders and check-ins
-- are recurring tasks. In the MVP the owner writes these by hand; the agent does
-- not propose them yet.
CREATE TABLE task (
  id            TEXT PRIMARY KEY,
  home_id       TEXT NOT NULL REFERENCES home(id) ON DELETE CASCADE,
  project_id    TEXT REFERENCES project(id) ON DELETE SET NULL,
  item_id       TEXT REFERENCES item(id) ON DELETE SET NULL,
  title         TEXT NOT NULL,
  due           TEXT,
  recurrence    TEXT,                      -- none | monthly | quarterly | semiannual | annual
  done_at       TEXT,
  source_observation_id TEXT REFERENCES observation(id),
  stated_by     TEXT NOT NULL DEFAULT 'owner',
  confidence    REAL NOT NULL DEFAULT 1.0,
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);
CREATE INDEX task_due_idx ON task(home_id, done_at, due);

-- ---------------------------------------------------------------------------
-- Paper trail. Document, money, and contact attach polymorphically —
-- (attached_to_type, attached_to_id) points at a home, item, project, or issue.
-- ---------------------------------------------------------------------------

CREATE TABLE document (
  id            TEXT PRIMARY KEY,
  home_id       TEXT NOT NULL REFERENCES home(id) ON DELETE CASCADE,
  kind          TEXT NOT NULL,             -- warranty | manual | receipt | inspection | permit | loan
  file_ref      TEXT,
  extracted     TEXT,                      -- JSON
  expires       TEXT,
  attached_to_type TEXT,
  attached_to_id   TEXT,
  source_observation_id TEXT REFERENCES observation(id),
  stated_by     TEXT NOT NULL DEFAULT 'owner',
  confidence    REAL NOT NULL DEFAULT 1.0,
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);
CREATE INDEX document_attached_idx ON document(attached_to_type, attached_to_id);

CREATE TABLE money (
  id            TEXT PRIMARY KEY,
  home_id       TEXT NOT NULL REFERENCES home(id) ON DELETE CASCADE,
  kind          TEXT NOT NULL,             -- loan | payment | insurance | quote | cost | warranty
  amount        REAL,
  cadence       TEXT,                      -- once | monthly | annual
  next_due      TEXT,
  counterparty_id TEXT REFERENCES contact(id) ON DELETE SET NULL,
  attached_to_type TEXT,
  attached_to_id   TEXT,
  source_observation_id TEXT REFERENCES observation(id),
  stated_by     TEXT NOT NULL DEFAULT 'owner',
  confidence    REAL NOT NULL DEFAULT 1.0,
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);
CREATE INDEX money_attached_idx ON money(attached_to_type, attached_to_id);

CREATE TABLE contact (
  id            TEXT PRIMARY KEY,
  home_id       TEXT NOT NULL REFERENCES home(id) ON DELETE CASCADE,
  role          TEXT,                      -- contractor | inspector | lender | insurer
  name          TEXT NOT NULL,
  phone         TEXT,
  notes         TEXT,
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);

-- The efficacy dataset, built passively: energy use, runtime, failure events.
-- Phase 3 in the app; in the schema from the start, because retrofitting a
-- measurement history is impossible — you can only start keeping one.
CREATE TABLE measurement (
  id            TEXT PRIMARY KEY,
  item_id       TEXT NOT NULL REFERENCES item(id) ON DELETE CASCADE,
  metric        TEXT NOT NULL,             -- kwh | runtime_hours | temp_f | failure | ...
  value         REAL,
  unit          TEXT,
  measured_at   TEXT NOT NULL,
  source        TEXT,                      -- meter | owner | device | inspection
  created_at    TEXT NOT NULL
);
CREATE INDEX measurement_item_idx ON measurement(item_id, metric, measured_at DESC);

-- Free-form relationships the schema didn't anticipate ("this vent serves that
-- room", "this receipt covers that project"). The escape hatch that keeps the
-- rest of the schema from growing a column every time reality is odd.
CREATE TABLE link (
  id            TEXT PRIMARY KEY,
  home_id       TEXT NOT NULL REFERENCES home(id) ON DELETE CASCADE,
  from_type     TEXT NOT NULL,
  from_id       TEXT NOT NULL,
  to_type       TEXT NOT NULL,
  to_id         TEXT NOT NULL,
  kind          TEXT,
  created_at    TEXT NOT NULL
);
CREATE INDEX link_from_idx ON link(from_type, from_id);
CREATE INDEX link_to_idx   ON link(to_type, to_id);

-- Observations mention items; the join is many-to-many and is how a photo stays
-- attached to everything it turned out to be about.
CREATE TABLE observation_item (
  observation_id TEXT NOT NULL REFERENCES observation(id) ON DELETE CASCADE,
  item_id        TEXT NOT NULL REFERENCES item(id) ON DELETE CASCADE,
  PRIMARY KEY (observation_id, item_id)
);

-- ---------------------------------------------------------------------------
-- Semantic layer
--
-- Rule 5: this is not a separate store. Embeddings on space, item, and observation
-- plus the link table let "the leak under the upstairs bathroom" resolve to rows.
--
-- Postgres:  CREATE EXTENSION vector;
--            ALTER TABLE embedding ALTER COLUMN vec TYPE vector(1024) USING ...;
--            CREATE INDEX ON embedding USING hnsw (vec vector_cosine_ops);
-- SQLite:    keep the BLOB and brute-force the cosine in application code until it
--            hurts, then reach for sqlite-vec. At one household's scale it does
--            not hurt.
-- ---------------------------------------------------------------------------
CREATE TABLE embedding (
  id            TEXT PRIMARY KEY,
  home_id       TEXT NOT NULL REFERENCES home(id) ON DELETE CASCADE,
  target_type   TEXT NOT NULL,             -- space | item | observation
  target_id     TEXT NOT NULL,
  text          TEXT NOT NULL,             -- what was embedded, kept for debugging
  vec           BLOB NOT NULL,
  model         TEXT NOT NULL,
  created_at    TEXT NOT NULL
);
CREATE INDEX embedding_target_idx ON embedding(target_type, target_id);

-- ---------------------------------------------------------------------------
-- Views the app leans on
-- ---------------------------------------------------------------------------

-- The inbox: cards waiting on the owner, newest first.
CREATE VIEW pending_proposal AS
  SELECT * FROM proposal WHERE status = 'pending' ORDER BY created_at DESC;

-- Rule 4, as a query. A candidate proposal whose signature appears here has already
-- been turned down; only a different value counts as new evidence.
CREATE VIEW dismissed_signature AS
  SELECT home_id, signature, MAX(decided_at) AS dismissed_at
  FROM proposal WHERE status = 'dismissed'
  GROUP BY home_id, signature;

-- What's due, and what's overdue.
CREATE VIEW open_task AS
  SELECT * FROM task WHERE done_at IS NULL ORDER BY (due IS NULL), due;
