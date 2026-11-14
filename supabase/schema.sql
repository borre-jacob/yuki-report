-- Yuki Report: members' shared pins, hikes and lines, and synced favourites (Supabase / PostgreSQL).
-- Run once in the Supabase dashboard: SQL Editor → New query → paste → Run. Safe to run again.
--
-- What is stored: for a pin only the position and the resort, plus whose it is (so members can remove their own);
-- no time or date. For a hike (the way up) or a line (the way down) the track: positions and heights, no times.
-- For a favourite the resort. A member's pins and favourites go when the account is deleted.
-- Who sees what (row level security): logged-in members see every pin and can add and remove their own;
-- visitors who are not logged in only get the number of pins per resort (pin_counts), never the positions.

create table if not exists public.pins (
  id      uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  resort  text not null check (resort ~ '^[a-z0-9]{1,40}$'),
  lat     double precision not null check (lat between -90 and 90),
  lon     double precision not null check (lon between -180 and 180)
);
create index if not exists pins_resort on public.pins (resort);

create table if not exists public.favourites (
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  resort  text not null check (resort ~ '^[a-z0-9]{1,40}$'),
  primary key (user_id, resort)
);

alter table public.pins enable row level security;
alter table public.favourites enable row level security;

-- The project does not expose new tables automatically, so the Data API gets access here, and only what the
-- policies below allow (visitors who are not logged in get nothing from the tables themselves)
revoke all on public.pins, public.favourites from anon, authenticated;
grant select, insert, delete on public.pins to authenticated;
grant select, insert, delete on public.favourites to authenticated;

drop policy if exists "members see all pins" on public.pins;
create policy "members see all pins" on public.pins for select to authenticated using (true);
drop policy if exists "members add own pins" on public.pins;
create policy "members add own pins" on public.pins for insert to authenticated with check (user_id = auth.uid());
drop policy if exists "members remove own pins" on public.pins;
create policy "members remove own pins" on public.pins for delete to authenticated using (user_id = auth.uid());

drop policy if exists "own favourites" on public.favourites;
create policy "own favourites" on public.favourites for all to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());

-- At most 30 pins per member and resort, against mistakes and spam
create or replace function public.pins_limit() returns trigger language plpgsql as $$
begin
  if (select count(*) from public.pins where user_id = new.user_id and resort = new.resort) >= 30 then
    raise exception 'too many pins for this resort';
  end if;
  return new;
end $$;
drop trigger if exists pins_limit on public.pins;
create trigger pins_limit before insert on public.pins for each row execute function public.pins_limit();

-- The number of shared pins for a resort, for everyone (also not logged in): only the count, no positions
create or replace function public.pin_counts(r text) returns integer
  language sql stable security definer set search_path = public as $$
  select count(*)::integer from public.pins where resort = r
$$;
revoke all on function public.pin_counts(text) from public;
grant execute on function public.pin_counts(text) to anon, authenticated;

-- Hikes (the way up from a start point) and lines (the way down), recorded with the phone's GPS or from a GPX file.
-- pts is [[lat, lon, height in metres or null], …], simplified by the app; no times. A member can keep a track to
-- themselves (shared = false) or share it with the other members.
create table if not exists public.tracks (
  id      uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  resort  text not null check (resort ~ '^[a-z0-9]{1,40}$'),
  kind    text not null check (kind in ('hike', 'line')),
  shared  boolean not null default true,
  pts     jsonb not null check (jsonb_typeof(pts) = 'array' and jsonb_array_length(pts) between 2 and 3000)
);
create index if not exists tracks_resort on public.tracks (resort);
-- Drawn on the map by hand (true) rather than recorded with GPS or loaded from a GPX file
alter table public.tracks add column if not exists drawn boolean not null default false;
alter table public.tracks enable row level security;
revoke all on public.tracks from anon, authenticated;
grant select, insert, delete on public.tracks to authenticated;
grant update (shared) on public.tracks to authenticated;

drop policy if exists "members see shared and own tracks" on public.tracks;
create policy "members see shared and own tracks" on public.tracks for select to authenticated
  using (shared or user_id = auth.uid());
drop policy if exists "members add own tracks" on public.tracks;
create policy "members add own tracks" on public.tracks for insert to authenticated with check (user_id = auth.uid());
drop policy if exists "members change own tracks" on public.tracks;
create policy "members change own tracks" on public.tracks for update to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());
drop policy if exists "members remove own tracks" on public.tracks;
create policy "members remove own tracks" on public.tracks for delete to authenticated using (user_id = auth.uid());

-- At most 100 tracks per member and resort
create or replace function public.tracks_limit() returns trigger language plpgsql as $$
begin
  if (select count(*) from public.tracks where user_id = new.user_id and resort = new.resort) >= 100 then
    raise exception 'too many tracks for this resort';
  end if;
  return new;
end $$;
drop trigger if exists tracks_limit on public.tracks;
create trigger tracks_limit before insert on public.tracks for each row execute function public.tracks_limit();

-- What members have shared for a resort, for everyone (also not logged in): only the numbers
create or replace function public.shared_counts(r text) returns json
  language sql stable security definer set search_path = public as $$
  select json_build_object(
    'pins',  (select count(*) from public.pins where resort = r),
    'hikes', (select count(*) from public.tracks where resort = r and shared and kind = 'hike'),
    'lines', (select count(*) from public.tracks where resort = r and shared and kind = 'line'))
$$;
revoke all on function public.shared_counts(text) from public;
grant execute on function public.shared_counts(text) to anon, authenticated;

-- A member deletes their own account; pins, tracks and favourites go with it (on delete cascade)
create or replace function public.delete_my_account() returns void
  language sql security definer set search_path = public, auth as $$
  delete from auth.users where id = auth.uid()
$$;
revoke all on function public.delete_my_account() from public;
grant execute on function public.delete_my_account() to authenticated;

-- Make the Data API see the new tables and functions right away
notify pgrst, 'reload schema';
