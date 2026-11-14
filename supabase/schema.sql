-- Yuki Report: members' shared pins and synced favourites (Supabase / PostgreSQL).
-- Run once in the Supabase dashboard: SQL Editor → New query → paste → Run. Safe to run again.
--
-- What is stored: for a pin only the position and the resort, plus whose it is (so members can remove their own);
-- no time or date. For a favourite the resort. A member's pins and favourites go when the account is deleted.
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

-- A member deletes their own account; pins and favourites go with it (on delete cascade)
create or replace function public.delete_my_account() returns void
  language sql security definer set search_path = public, auth as $$
  delete from auth.users where id = auth.uid()
$$;
revoke all on function public.delete_my_account() from public;
grant execute on function public.delete_my_account() to authenticated;

-- Make the Data API see the new tables and functions right away
notify pgrst, 'reload schema';
