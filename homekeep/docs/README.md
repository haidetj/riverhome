# Homekeep — spec of record

These are the handoff addendum documents, unchanged, plus the decisions that were
open when they were written. The app in `../index.html` implements the MVP row of
the roadmap in `04_merge_notes.md`; `../schema.sql` is `03_data_model.md` expressed
as DDL.

## Contents

| File | What it is |
|---|---|
| `03_data_model.md` | The ledger: entities, fields, relationships, and the six rules that make it work |
| `04_merge_notes.md` | The three edits to the base package, the revised roadmap with a success test per phase, and the leans on the five open questions |
| `diagrams/pipeline_propose_loop.svg` | The capture → extract → **propose** → decide loop, with Propose drawn explicitly |
| `diagrams/storage_vault_layers.svg` | Household vault → anonymizer → stats pool |
| `diagrams/ledger_erd.mermaid` | Entity-relationship diagram for the core eight tables |

## Decisions taken since

**Naming — resolved.** HomeIQ / HomeOps / HomeEO → **Homekeep**. Plain compound
English, same shape as RiverHome next door in this repo, and it says what the thing
does: it keeps the record of your home. Nothing in the spec depended on the choice.

**Storage — resolved per merge note #2, and implemented.** Photos are kept, because
they are the record. Voice audio is out of the MVP entirely; when it lands, the
audio is discarded after transcription. Everything is exportable and deletable in
one tap. The v0 vault is the browser's own IndexedDB on the owner's device — no
server, so "per-household keys" is not yet a question the app has to answer.

**Proposal `change` shape — resolved for v0** (listed as deliberately open). A
proposal carries a full field set for the target row, not a JSON patch: `op`
(`create` | `update`), `target_type`, `target_id`, and `fields`. Editing a proposal
before accepting it is then just editing a form, which is what makes the edit button
cheap enough to ship in the MVP.

## Still deliberately open

Unchanged from `03_data_model.md`: whether Issue and Task collapse into one type,
how deep Item nesting goes before it annoys, and whether Inspection is its own
entity. The MVP does not force any of these — it ships Space and Item only, so the
first real photos get to argue for the rest.
