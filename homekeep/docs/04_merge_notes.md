# 04 — Merge Notes

Verdict: their package is the base. Keep their brief, their two-zone framing, their tone rules, and their open questions. Make the three edits below, add `03_data_model.md`, and the spec is complete.

## Three edits to their docs

### 1. Move the accept / edit / dismiss loop into the MVP
Their roadmap puts it in Phase 3 and their README's MVP slice omits it. The Proposal card is the mechanism that makes "no forms" true — without it the MVP either writes to the ledger silently or makes the user type things in. Ship a crude version in the MVP: one card type, three buttons.

### 2. Resolve the storage contradiction
`storage_architecture.svg` says "Ephemeral Processing — no raw media retained," then "Encrypted Storage — Media + Home Graph DB." Decision:
- Photos: kept, encrypted at rest, per-household keys. They are the record.
- Voice audio: discarded after transcription. Transcript kept.
- Owner can export or delete everything in one tap.

### 3. Add a success test per phase
A roadmap without a number to hit drifts. Revised table below.

## Revised roadmap

| Phase | Build | Prove |
|---|---|---|
| MVP | Photo → Proposal card (accept / edit / dismiss), text chat, ledger with Home / Space / Item / Observation / Proposal, manual reminders | Does it feel like texting a friend? Would you send a second photo? |
| Phase 2 | Push-to-talk voice, scheduler, Issue / Project / Task, warranty and loan records, headless research agent | Still sending photos in week 3? |
| Phase 3 | Age and monitoring alerts, Measurement (efficacy data), contractor share links, live-call voice | Retention holds, first paid users |
| Phase 4 | Anonymizer, stats pool, partner APIs (insurers, retailers) | First data partner signed |

## Keep from theirs (already right)
- Accept / edit / dismiss — three states, not two
- "Dismissed items don't resurface without new evidence"
- One question at a time; celebrates progress; always an easy dismiss
- Regional renovation-demand signals as a revenue line
- Household zone / Business Insights Layer naming, one-way flow

## Add from this side
- Provenance and certainty on every record (see `03_data_model.md`)
- Measurement entity — the efficacy dataset is built passively from it
- Contractor handoff: a scoped project brief the owner can share for quotes (marketplace later)
- Proposal loop drawn explicitly in the pipeline diagram

## Answers to their open questions (leans, not final)

| # | Question | Lean |
|---|---|---|
| 1 | Entry point | Chat channel first (SMS / WhatsApp). Matches "text a friend." App when the ledger needs a view. |
| 2 | Voice | Push-to-talk notes first. Live call later. Same transcript pipeline either way. |
| 3 | Data model | Relational + embeddings + Link table. Not a graph DB. |
| 4 | On-device vs cloud | Cloud first, per-household keys. On-device is a Phase 3 pitch, not a v0 constraint. |
| 5 | Naming | Resolve HomeIQ vs HomeOps before the repo exists. "Your home's memory" is the stronger angle of the two they suggested. |

## Agent rules (merged)
- Suggests once, then waits. No nagging.
- Every change is a card. Nothing lands silently.
- Dismissed stays dismissed until new evidence.
- Asks like a contractor: how old, where, what's it connected to, how bad. One question at a time.
- Celebrates progress without inflating it.
- Research never writes directly. Findings become cards.
