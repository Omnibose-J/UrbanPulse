-- Weekend reminder subscriptions (design spec 5.15, build contract 6.5). One row per browser push endpoint.
-- Written only by the web app's service role (`/api/push/subscribe`), read by the Friday cron route.
-- Applied with `supabase migration up` locally and `scripts/cloud/30_db_push.ps1` on the hosted database.

create table push_subscriptions (
  endpoint      text primary key,
  subscription  jsonb not null,
  locale        text not null check (locale in ('ko', 'en')),
  place_ids     text[] not null,
  tolerance     text not null check (tolerance in ('calm', 'moderate', 'busy_ok')),
  purpose       text not null check (purpose in ('sight', 'food', 'shop')),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  last_sent_at  timestamptz,
  check (cardinality(place_ids) between 1 and 20)
);
alter table push_subscriptions enable row level security;
revoke all on table push_subscriptions from anon, authenticated;
