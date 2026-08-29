# Homekeep

**Your home's memory.** Send it a photo of the water heater. It reads the label,
drafts a card — *Add: gas water heater, A.O. Smith, installed ~2014 (my guess from
the photo)* — and waits. You accept it, correct it, or dismiss it. That's the whole
product.

> _Nothing lands silently. Every change is a card._

No forms. No forty-field asset register to fill in on a Sunday. The ledger fills
itself one photo at a time, and it never writes anything you didn't agree to.

## How it works

1. **Capture.** A photo, a typed note, or both. The observation saves *first and
   always* — before the agent runs, and whether or not it succeeds. It is the
   provenance every later row points at.
2. **Propose.** The agent reads it and drafts cards: a new space, a new item, a
   correction to something already on the record. It says what it saw and how sure
   it is.
3. **Decide.** Accept · Edit · Dismiss. Three buttons, three states.
   - **Accept** writes the row, stamped as the agent's inference at its stated
     confidence.
   - **Edit** writes what *you* say instead — recorded as stated by you, at full
     confidence, outranking anything the agent thought.
   - **Dismiss** keeps the card and remembers the refusal. The same claim about the
     same thing does not come back. A *different* value is new evidence and may.

The house tab is the ledger: spaces, the items in them, and who said so. The
reminders tab is the manual half — filter changes, gutters, the annual service —
with recurring ones rolling forward when you tick them off.

## The rules it actually enforces

These are from `docs/03_data_model.md`, and they are structural here rather than
aspirational:

- **Every record carries provenance.** `source_observation_id`, `stated_by`
  (owner / agent / research), and `confidence`, on every row, shown on every card.
- **Uncertain values keep their uncertainty.** `installed: 2014` travels with
  `installed_certainty: estimated_from_photo`, which is what tells the agent it's
  worth asking about later.
- **One write path.** `commit()` is the only function that touches the ledger, and
  it always stamps the proposal that authorised it. An owner typing into a form is
  the same path with the card pre-accepted — so the audit trail has no holes.
- **Owner outranks agent.** Correcting anything re-stamps it as yours at
  confidence 1.
- **Dismissed stays dismissed**, by signature, not by vibes.

## What's in this MVP

The MVP row of the roadmap in `docs/04_merge_notes.md`, and no more: photo →
proposal card with accept / edit / dismiss, text chat, a ledger of
Home / Space / Item / Observation / Proposal, and manual reminders. Voice, issues,
projects, research, and the anonymised stats pool are later phases and are
deliberately absent — though the schema has room for them already.

The test the roadmap sets for this phase: *does it feel like texting a friend, and
would you send a second photo?*

## The agent, and doing without one

With an Anthropic API key, Claude reads your photos and drafts the cards. Without
one, Homekeep still keeps everything: the observation saves, the photo is kept, and
you get a blank card to fill in yourself — the loop closes either way, just with
more typing. The key is entered on-device, stored in this browser, and sent only to
Anthropic, with one photo at a time and only at the moment it's being read.

## Your data

The vault is this browser on this device — IndexedDB, no server, nothing synced.

- **Photos are kept**, because they *are* the record: before-and-after, condition
  evidence, insurance proof.
- **Voice audio would be discarded** after transcription — that decision is made,
  but voice isn't in this phase.
- **Export or delete everything in one tap**, in ⚙︎. Export is a single JSON file
  with the whole ledger and every photo inline.

## Run it

```bash
python3 -m http.server 8000    # then open http://localhost:8000/homekeep/
```

Self-contained PWA (`index.html` + `manifest.json` + `sw.js` + `icon.svg`) —
installable to a phone home screen; the app shell works offline, and so does
everything except the agent.

## The files

| File | What it is |
|---|---|
| `index.html` | The whole app — vanilla JS, no build step |
| `schema.sql` | The ledger as SQL: every entity, provenance columns, and the views the rules imply. SQLite-flavoured, Postgres notes inline |
| `docs/` | The spec this was built from, plus the decisions taken since |

`schema.sql` is the destination. The app's IndexedDB stores use its exact field
names, so moving the ledger to real SQL is a transport change, not a migration of
meaning.

## The one rule

Homekeep suggests once, then waits. It doesn't nag, it doesn't re-litigate a
dismissal, and it doesn't put anything on the record that you didn't put there.
**If it's on the ledger, you said yes to it.**
