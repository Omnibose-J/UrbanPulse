-- pgTAP: schema, primary keys, check constraints, and denial of anon/authenticated. Run: supabase test db
begin;
select no_plan();

-- every table exists with exactly its primary key
select has_table('public', t, t || ' exists')
from unnest(array[
  'places','live_obs','commerce_obs','city_fcst','holidays','level_thresholds','tier_b_profile',
  'lively_profile','forecast_hourly','recommendations','similar_places','forecast_log','eval_daily',
  'reco_eval_daily','strip_eval_daily','model_registry','job_runs']) t;

select col_is_pk('public', 'places', 'id', 'places pk');
select col_is_pk('public', 'live_obs', array['place_id','ts'], 'live_obs pk');
select col_is_pk('public', 'commerce_obs', array['place_id','ts'], 'commerce_obs pk');
select col_is_pk('public', 'city_fcst', array['place_id','target_ts'], 'city_fcst pk');
select col_is_pk('public', 'holidays', 'date', 'holidays pk');
select col_is_pk('public', 'level_thresholds', 'place_id', 'level_thresholds pk');
select col_is_pk('public', 'tier_b_profile', array['place_id','day_type','hour'], 'tier_b_profile pk');
select col_is_pk('public', 'lively_profile', array['place_id','day_type','hour'], 'lively_profile pk');
select col_is_pk('public', 'forecast_hourly', array['place_id','target_ts'], 'forecast_hourly pk');
select col_is_pk('public', 'recommendations', array['place_id','date','tolerance','purpose'], 'recommendations pk');
select col_is_pk('public', 'similar_places', array['place_id','other_id'], 'similar_places pk');
select col_is_pk('public', 'forecast_log', array['place_id','issued_date','target_ts'], 'forecast_log pk');
select col_is_pk('public', 'eval_daily', array['date','horizon_d','segment'], 'eval_daily pk');
select col_is_pk('public', 'reco_eval_daily', array['date','place_id','purpose','tolerance'], 'reco_eval_daily pk');
select col_is_pk('public', 'strip_eval_daily', array['date','place_id','purpose','tolerance'], 'strip_eval_daily pk');
select col_is_pk('public', 'model_registry', array['name','version'], 'model_registry pk');
select col_is_pk('public', 'job_runs', 'id', 'job_runs pk');

-- a place to hang FK rows on (rolled back with the transaction)
insert into places (id, tier, name, serve_state) values ('POI001', 'A1', '성수카페거리', 'on');

-- each check constraint rejects one bad row (SQLSTATE 23514)
select throws_ok($$insert into places (id, tier, name) values ('X', 'C', 'bad tier')$$, '23514', null, 'places.tier');
select throws_ok($$insert into live_obs (place_id, ts, pop_min, pop_max, level) values ('POI001', now(), 1, 2, 4)$$,
  '23514', null, 'live_obs.level');
select throws_ok($$insert into level_thresholds (place_id, t1, t2, t3, based_on_days) values ('POI001', 5, 3, 9, 30)$$,
  '23514', null, 'level_thresholds t1 <= t2');
select throws_ok($$insert into forecast_hourly (place_id, target_ts, issued_ts, source, ready)
  values ('POI001', now(), now(), 'model', true)$$, '23514', null, 'forecast_hourly ready needs level');

-- recommendations: off rows carry only a reason; on rows carry the computed columns
select throws_ok($$insert into recommendations (place_id, date, tolerance, purpose, state, off_reason, windows)
  values ('POI001', current_date, 'moderate', 'sight', 'off', 'failed', '[]'::jsonb)$$,
  '23514', null, 'recommendations off + windows');
select throws_ok($$insert into recommendations (place_id, date, tolerance, purpose, state, off_reason, windows, no_window, hours, strip_mode)
  values ('POI001', current_date, 'moderate', 'sight', 'on', 'failed', '[]'::jsonb, false,
          (select jsonb_agg(jsonb_build_object('h', h)) from generate_series(9, 23) h), 'windows_only')$$,
  '23514', null, 'recommendations on + off_reason');
select throws_ok($$insert into recommendations (place_id, date, tolerance, purpose, state, windows, no_window, hours, strip_mode)
  values ('POI001', current_date, 'moderate', 'sight', 'on', '[]'::jsonb, false,
          (select jsonb_agg(jsonb_build_object('h', h)) from generate_series(9, 22) h), 'windows_only')$$,
  '23514', null, 'recommendations hours must have 15 cells');
select throws_ok($$insert into recommendations (place_id, date, tolerance, purpose, state, off_reason, strip_mode)
  values ('POI001', current_date, 'moderate', 'sight', 'off', 'failed', 'windows_only')$$,
  '23514', null, 'recommendations off + strip_mode');
select lives_ok($$insert into recommendations (place_id, date, tolerance, purpose, state, windows, no_window, hours, strip_mode)
  values ('POI001', current_date, 'moderate', 'sight', 'on', '[]'::jsonb, false,
          (select jsonb_agg(jsonb_build_object('h', h)) from generate_series(9, 23) h), 'windows_only')$$,
  'recommendations valid on row');
select lives_ok($$insert into recommendations (place_id, date, tolerance, purpose, state, off_reason)
  values ('POI001', current_date, 'calm', 'food', 'off', 'failed')$$, 'recommendations valid off row');

-- evaluation counters
select throws_ok($$insert into reco_eval_daily (date, place_id, purpose, tolerance, n_hours, n_lively, n_crowd_ok, chance_hours, chance_lively)
  values (current_date, 'POI001', 'sight', 'busy_ok', 3, 3, 3, 15, 9)$$,
  '23514', null, 'reco_eval_daily busy_ok has no crowd count');
select throws_ok($$insert into strip_eval_daily (date, place_id, purpose, tolerance, n_ok, n_ok_lively, n_ok_crowd_ok, n_avoid, n_avoid_unfit)
  values (current_date, 'POI001', 'sight', 'busy_ok', 10, 9, 9, 5, 3)$$,
  '23514', null, 'strip_eval_daily busy_ok has no crowd count');
select throws_ok($$insert into strip_eval_daily (date, place_id, purpose, tolerance, n_ok, n_ok_lively, n_ok_crowd_ok, n_avoid, n_avoid_unfit)
  values (current_date, 'POI001', 'sight', 'moderate', 10, 9, 9, 5, 6)$$,
  '23514', null, 'strip_eval_daily n_avoid_unfit <= n_avoid');

-- one active model per name
insert into model_registry (name, version, trained_range, horizons, metrics, artifact_uri, active)
  values ('ratio_v1', '1', '2023-01..2026-07', '{0,1,2,3,4,5,6,7}', '{}'::jsonb, 'models/ratio_v1', true);
select throws_ok($$insert into model_registry (name, version, trained_range, horizons, metrics, artifact_uri, active)
  values ('ratio_v1', '2', '2023-01..2026-08', '{0,1,2,3,4,5,6,7}', '{}'::jsonb, 'models/ratio_v1', true)$$,
  '23505', null, 'model_registry second active row rejected');

-- anon and authenticated can read nothing; RLS is on everywhere
select ok(not has_table_privilege('anon', format('public.%I', t), 'SELECT'), 'anon cannot select ' || t)
from unnest(array[
  'places','live_obs','commerce_obs','city_fcst','holidays','level_thresholds','tier_b_profile',
  'lively_profile','forecast_hourly','recommendations','similar_places','forecast_log','eval_daily',
  'reco_eval_daily','strip_eval_daily','model_registry','job_runs']) t;
select ok(not has_table_privilege('authenticated', format('public.%I', t), 'SELECT'), 'authenticated cannot select ' || t)
from unnest(array[
  'places','live_obs','commerce_obs','city_fcst','holidays','level_thresholds','tier_b_profile',
  'lively_profile','forecast_hourly','recommendations','similar_places','forecast_log','eval_daily',
  'reco_eval_daily','strip_eval_daily','model_registry','job_runs']) t;
select ok((select relrowsecurity from pg_class where oid = format('public.%I', t)::regclass), 'rls on ' || t)
from unnest(array[
  'places','live_obs','commerce_obs','city_fcst','holidays','level_thresholds','tier_b_profile',
  'lively_profile','forecast_hourly','recommendations','similar_places','forecast_log','eval_daily',
  'reco_eval_daily','strip_eval_daily','model_registry','job_runs']) t;

select * from finish();
rollback;
