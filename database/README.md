# Part 9: Storage (Supabase)

Where results and labels live: particle rows, the review history (who labelled what, expert or community), model versions, and possibly photos or crops. Snapshots of the database are exported for retraining and publishing.

**Method:** a Postgres database with Storage and Auth, used straight from the browser with the Supabase JS client (`web/src/storage/`). Supabase is the only backend.

## In → Out

| In | Out |
|---|---|
| Particle rows from the app (part 8) | A shared, queryable record of every sample |
| Review decisions (part 6) | Database snapshots for retraining (part 10) and for publishing (e.g. Zenodo with a DOI) |
| Reviewer sign-in | |

## Rules already decided

- **Row Level Security on every table.** The browser only ever has the public anon key, never the service-role key.
- **Supabase Auth** for reviewers, with a role (expert or community) recorded on every label.
- Free tier only. Keep exported snapshots as backups, and plan for the free tier's limits and inactive-project pausing.

## What exists

| File | Does |
|---|---|
| `migrations/0001_draft_schema.sql` | **Draft** tables and RLS, to discuss. Not applied anywhere. It waits on Drive open question 9b (what is stored). |

## To build

- [ ] **Decide what is stored** (Drive 9b): full photos, crops only, or only measurement rows. This affects storage limits and privacy.
- [ ] **Check the free-tier limits** against the expected use, and how to keep the project from pausing (9c).
- [ ] **Finalize the schema** from the draft; the columns follow [docs/OUTPUT_CSV.md](../docs/OUTPUT_CSV.md).
- [ ] **Write the RLS policies:**
  - anyone signed in can add their own runs
  - reviewers can add labels
  - only experts can mark gold-set particles
- [ ] **Snapshot export:** one versioned file per retraining (rows + labels + model versions).
- [ ] **Data licence and consent terms** for contributed photos and labels (open question 9), shown at upload.
- [ ] **A data retention policy.**
