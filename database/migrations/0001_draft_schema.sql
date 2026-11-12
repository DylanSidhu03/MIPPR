-- Part 9: DRAFT schema for discussion. Not applied anywhere.
-- Waits on Drive open question 9b (what is stored: photos, crops or rows only).
-- Columns follow docs/OUTPUT_CSV.md; only the main ones are listed here.
-- Rule: Row Level Security on every table; the browser only has the anon key.

create table samples (
  id            uuid primary key default gen_random_uuid(),
  sample_id     text not null,            -- typed by the user, e.g. S042
  lab           text,
  site          text,
  owner         uuid not null references auth.users (id),
  created_at    timestamptz not null default now()
);

create table images (
  id              uuid primary key default gen_random_uuid(),
  sample          uuid not null references samples (id) on delete cascade,
  image_id        text not null,          -- file name + hash, e.g. particle-3f9c21ab
  picture_label   text not null,          -- e.g. S042-P01
  background_type text not null check (background_type in ('white_grid', 'black_grid', 'checkerboard')),
  mm_per_px       double precision not null,
  scale_source    text not null check (scale_source in ('markers', 'user_corrected')),  -- user_corrected: 100 mm line entered
  storage_path    text,                   -- photo in Supabase Storage, if stored (9b)
  app_version     text not null,
  processed_at    timestamptz not null,
  operator        text,
  setup           text,
  taken_on        date
);

create table particles (
  id                    uuid primary key default gen_random_uuid(),
  image                 uuid not null references images (id) on delete cascade,
  particle_id           text not null,    -- box label, e.g. B4
  particle_ref          text not null,    -- e.g. S042-P01-B4
  length_mm             double precision,
  width_mm              double precision,
  fiber_length_mm       double precision,
  area_mm2              double precision,
  perimeter_mm          double precision,
  aspect_ratio          double precision,
  circularity           double precision,
  solidity              double precision,
  opacity               double precision,
  color_L double precision, color_a double precision, color_b double precision,
  color_label           text,
  color_confidence      double precision,
  color_secondary       text,
  color_secondary_fraction double precision,
  morphology_label      text,
  morphology_source     text,             -- rule or model
  morphology_confidence double precision,
  review_reason         text,             -- semicolon list of flags
  review_status         text not null default 'auto',  -- auto, confirmed, corrected, rejected
  crop_path             text,             -- crop in Storage, if stored (9b)
  model_version         text,
  color_rules_version   text,
  unique (image, particle_id)
);

-- Every review action is kept, so labels can be traced and weighted (expert vs community).
create table labels (
  id              uuid primary key default gen_random_uuid(),
  particle        uuid not null references particles (id) on delete cascade,
  reviewer        uuid not null references auth.users (id),
  reviewer_role   text not null,          -- expert or community
  action          text not null,          -- confirm, reject, relabel, edit_outline, tag
  color_label     text,
  morphology_label text,
  tags            jsonb,                  -- e.g. {"tar_like": true, "flag_bundle": true}
  in_gold_set     boolean not null default false,  -- experts only (policy to write)
  created_at      timestamptz not null default now()
);

create table model_versions (
  version         text primary key,       -- e.g. morphology-2027.01
  kind            text not null,          -- morphology model, or colour rules
  trained_on      text,                   -- snapshot name
  gold_set_score  jsonb,                  -- accuracy per class on the fixed gold set
  approved        boolean not null default false,
  created_at      timestamptz not null default now()
);

alter table samples        enable row level security;
alter table images         enable row level security;
alter table particles      enable row level security;
alter table labels         enable row level security;
alter table model_versions enable row level security;

-- Policies still to write (see database/README.md). Example: owners read and write their own samples.
create policy "own samples" on samples
  for all using (owner = auth.uid()) with check (owner = auth.uid());
