-- Append-only recommendation log, activity normalisers, and measured-activity flag.
-- Applied with `supabase migration up`. Never `db reset` (that drops collected rows).

create table recommendation_log (
  place_id     text not null references places (id),
  issued_date  date not null,
  date         date not null,
  tolerance    text not null check (tolerance in ('calm', 'moderate', 'busy_ok')),
  purpose      text not null check (purpose in ('sight', 'food', 'shop', 'none')),
  state        text not null check (state in ('on', 'reference')),
  windows      jsonb not null,
  hours        jsonb not null,
  p90          real,
  lively_min   real,
  primary key (place_id, issued_date, date, tolerance, purpose)
);
create index recommendation_log_date_idx on recommendation_log (date);
alter table recommendation_log enable row level security;
revoke all on table recommendation_log from anon, authenticated;

create table lively_norm (
  place_id     text primary key references places (id),
  p90_all      real,
  p90_food     real,
  p90_shop     real,
  computed_at  timestamptz not null default now()
);
alter table lively_norm enable row level security;
revoke all on table lively_norm from anon, authenticated;

alter table forecast_hourly add column a_actual boolean not null default false;
