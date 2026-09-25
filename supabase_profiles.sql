-- Run this in the Supabase SQL Editor before using the application.
create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  name text not null check (char_length(name) between 1 and 120),
  email text not null unique,
  role text not null default 'Student' check (role in ('Student', 'Lecturer', 'Admin')),
  created_at timestamptz not null default now()
);

alter table public.profiles enable row level security;

-- SECURITY DEFINER avoids policy recursion while safely checking the caller's own role.
create or replace function public.is_admin()
returns boolean language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.profiles where id = auth.uid() and role = 'Admin');
$$;

create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, name, email, role)
  values (new.id, coalesce(nullif(trim(new.raw_user_meta_data ->> 'name'), ''), 'LectureMind user'), new.email,
    case when new.raw_user_meta_data ->> 'role' in ('Student', 'Lecturer') then new.raw_user_meta_data ->> 'role' else 'Student' end);
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users for each row execute procedure public.handle_new_user();

drop policy if exists "Users view own profile or admins view all" on public.profiles;
create policy "Users view own profile or admins view all" on public.profiles for select using (auth.uid() = id or public.is_admin());
drop policy if exists "Admins update other profiles" on public.profiles;
create policy "Admins update other profiles" on public.profiles for update using (public.is_admin()) with check (public.is_admin());
