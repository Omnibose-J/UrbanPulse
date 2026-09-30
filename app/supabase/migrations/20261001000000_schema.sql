-- UrbanPulse schema (build contract §3, refined in docs/sow/SOW-M0.md).
-- Times are timestamptz; `level` is 0 여유 / 1 보통 / 2 약간 붐빔 / 3 붐빔.
-- Enum-like columns are text + check so a new value never needs a type migration.

create table places (
  id             text primary key,
  tier           text not null check (tier in ('A1', 'A2', 'B')),
  name           text not null,
  name_en        text,
  category       text,
  gu             text,
  lat            double precision,
  lon            double precision,
  geom           jsonb,
  poi_code       text unique,
  station_codes  text[] not null default '{}',
  open_hours     jsonb,
  foreign_heavy  boolean not null default false,
  serve_state    text not null default 'preparing'
                 check (serve_state in ('on', 'preparing', 'off', 'experimental')),
  updated_at     timestamptz not null default now()
);

create table live_obs (
  place_id   text not null references places (id),
  ts         timestamptz not null,
  pop_min    integer not null,
  pop_max    integer not null,
  level      smallint not null check (level between 0 and 3),
  age_rates  jsonb,
  male_rate  real,
  primary key (place_id, ts),
  check (pop_min <= pop_max)
);
create index live_obs_ts_idx on live_obs (ts);

create table commerce_obs (
  place_id    text not null references places (id),
  ts          timestamptz not null,
  level       smallint check (level between 0 and 3),
  pay_cnt     integer not null,
  cat_counts  jsonb not null,
  primary key (place_id, ts)
);
create index commerce_obs_ts_idx on commerce_obs (ts);

create table city_fcst (
  place_id   text not null references places (id),
  target_ts  timestamptz not null,
  issued_ts  timestamptz not null,
  pop_min    integer not null,
  pop_max    integer not null,
  level      smallint not null check (level between 0 and 3),
  primary key (place_id, target_ts)
);

create table holidays (
  date     date primary key,
  name     text not null,
  name_en  text,
  kind     text not null check (kind in ('holiday', 'substitute', 'seol', 'chuseok'))
);

create table level_thresholds (
  place_id       text primary key references places (id),
  t1             real not null,
  t2             real not null,
  t3             real not null,
  based_on_days  integer not null,
  computed_at    timestamptz not null default now(),
  check (t1 <= t2 and t2 <= t3)
);

create table tier_b_profile (
  place_id  text not null references places (id),
  day_type  text not null check (day_type in ('weekday', 'sat', 'sun')),
  hour      smallint not null check (hour between 0 and 23),
  rel       real not null check (rel >= 0),
  primary key (place_id, day_type, hour)
);

create table lively_profile (
  place_id  text not null references places (id),
  day_type  text not null check (day_type in ('weekday', 'weekend', 'holiday', 'myeongjeol')),
  hour      smallint not null check (hour between 0 and 23),
  a_all     real,
  a_food    real,
  a_shop    real,
  n_days    integer not null,
  primary key (place_id, day_type, hour)
);

create table forecast_hourly (
  place_id   text not null references places (id),
  target_ts  timestamptz not null,
  issued_ts  timestamptz not null,
  source     text not null check (source in ('live', 'seoul', 'model', 'profile')),
  pop        real,
  rel        real,
  level      smallint check (level between 0 and 3),
  a_all      real,
  a_food     real,
  a_shop     real,
  stale      boolean not null default false,
  ready      boolean not null,
  primary key (place_id, target_ts),
  check (ready = false or level is not null)
);

create table recommendations (
  place_id      text not null references places (id),
  date          date not null,
  tolerance     text not null check (tolerance in ('calm', 'moderate', 'busy_ok')),
  purpose       text not null check (purpose in ('sight', 'food', 'shop', 'none')),
  state         text not null check (state in ('on', 'reference', 'off')),
  off_reason    text check (off_reason is null or off_reason in ('failed', 'unverified', 'myeongjeol', 'preparing')),
  windows       jsonb,
  no_window     boolean,
  hours         jsonb,
  strip_mode    text check (strip_mode is null or strip_mode in ('two_step', 'windows_only')),
  alt_dates     jsonb,
  alt_places    jsonb,
  generated_at  timestamptz not null default now(),
  primary key (place_id, date, tolerance, purpose),
  -- an off row carries only its reason; an on/reference row carries the computed columns
  check ((state = 'off') = (off_reason is not null)),
  check ((state = 'off') = (windows is null)),
  check ((state = 'off') = (hours is null)),
  check ((state = 'off') = (strip_mode is null)),
  check (hours is null or (jsonb_typeof(hours) = 'array' and jsonb_array_length(hours) = 15))
);
create index recommendations_map_idx on recommendations (date, tolerance, purpose);

create table similar_places (
  place_id  text not null references places (id),
  other_id  text not null references places (id),
  score     real not null,
  rank      smallint not null check (rank between 1 and 10),
  primary key (place_id, other_id),
  check (place_id <> other_id)
);

create table forecast_log (
  place_id       text not null references places (id),
  issued_date    date not null,
  target_ts      timestamptz not null,
  horizon_d      smallint not null check (horizon_d between 0 and 7),
  pred           real not null,
  baseline       real not null,
  model_version  text not null,
  primary key (place_id, issued_date, target_ts)
);
create index forecast_log_target_idx on forecast_log (target_ts);

create table eval_daily (
  date           date not null,
  horizon_d      smallint not null,
  segment        text not null check (segment in ('normal', 'holiday')),
  wape_model     real not null,
  wape_baseline  real not null,
  n              integer not null,
  primary key (date, horizon_d, segment)
);

create table reco_eval_daily (
  date           date not null,
  place_id       text not null references places (id),
  purpose        text not null check (purpose in ('sight', 'food', 'shop', 'none')),
  tolerance      text not null check (tolerance in ('calm', 'moderate', 'busy_ok')),
  n_hours        integer not null,
  n_lively       integer not null,
  n_crowd_ok     integer,
  chance_hours   integer not null,
  chance_lively  integer not null,
  primary key (date, place_id, purpose, tolerance),
  -- the busy_ok crowd promise is true by definition and is not scored
  check ((tolerance = 'busy_ok') = (n_crowd_ok is null))
);

create table strip_eval_daily (
  date            date not null,
  place_id        text not null references places (id),
  purpose         text not null check (purpose in ('sight', 'food', 'shop', 'none')),
  tolerance       text not null check (tolerance in ('calm', 'moderate', 'busy_ok')),
  n_ok            integer not null check (n_ok >= 0),
  n_ok_lively     integer check (n_ok_lively is null or n_ok_lively >= 0),
  n_ok_crowd_ok   integer check (n_ok_crowd_ok is null or n_ok_crowd_ok >= 0),
  n_avoid         integer not null check (n_avoid >= 0),
  n_avoid_unfit   integer not null check (n_avoid_unfit >= 0),
  primary key (date, place_id, purpose, tolerance),
  check ((tolerance = 'busy_ok') = (n_ok_crowd_ok is null)),
  check (n_ok_lively is null or n_ok_lively <= n_ok),
  check (n_avoid_unfit <= n_avoid)
);

create table model_registry (
  name           text not null,
  version        text not null,
  trained_range  text not null,
  horizons       smallint[] not null,
  metrics        jsonb not null,
  artifact_uri   text not null,
  active         boolean not null default false,
  created_at     timestamptz not null default now(),
  primary key (name, version)
);
create unique index model_registry_one_active_idx on model_registry (name) where active;

create table job_runs (
  id           bigint generated always as identity primary key,
  job          text not null,
  started_at   timestamptz not null default now(),
  finished_at  timestamptz,
  status       text not null check (status in ('running', 'ok', 'warn', 'fail')),
  detail       jsonb
);
create index job_runs_job_started_idx on job_runs (job, started_at desc);
