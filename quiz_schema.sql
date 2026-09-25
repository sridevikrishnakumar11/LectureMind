-- Run after the existing profiles/lectures schema. Uses the authenticated Supabase user, never a client-supplied user id.
create table if not exists public.quizzes (
  id uuid primary key default gen_random_uuid(), lecture_id uuid not null references public.lectures(id) on delete cascade,
  title text not null, questions jsonb not null check (jsonb_typeof(questions) = 'array'), created_at timestamptz not null default now()
);
create table if not exists public.quiz_attempts (
  id uuid primary key default gen_random_uuid(), quiz_id uuid not null references public.quizzes(id) on delete cascade,
  lecture_id uuid not null references public.lectures(id) on delete cascade, user_id uuid not null references auth.users(id) on delete cascade,
  score integer not null check (score >= 0), total_questions integer not null check (total_questions > 0), correct_answers integer not null check (correct_answers >= 0),
  percentage numeric(5,2) not null check (percentage between 0 and 100), answers jsonb not null check (jsonb_typeof(answers) = 'array'), created_at timestamptz not null default now(),
  check (score = correct_answers and score <= total_questions)
);
create index if not exists quizzes_lecture_id_idx on public.quizzes(lecture_id);
create index if not exists quiz_attempts_user_created_idx on public.quiz_attempts(user_id, created_at desc);
create index if not exists quiz_attempts_lecture_id_idx on public.quiz_attempts(lecture_id);
alter table public.quizzes enable row level security; alter table public.quiz_attempts enable row level security;
drop policy if exists "Owners access lecture quizzes" on public.quizzes;
create policy "Owners access lecture quizzes" on public.quizzes for all using (exists (select 1 from public.lectures l where l.id = lecture_id and l.user_id = auth.uid()) or public.is_admin()) with check (exists (select 1 from public.lectures l where l.id = lecture_id and l.user_id = auth.uid()));
drop policy if exists "Users view own quiz attempts" on public.quiz_attempts;
create policy "Users view own quiz attempts" on public.quiz_attempts for select using (user_id = auth.uid() or public.is_admin());
drop policy if exists "Students create their own quiz attempts" on public.quiz_attempts;
create policy "Students create their own quiz attempts" on public.quiz_attempts for insert with check (user_id = auth.uid() and exists (select 1 from public.lectures l where l.id = lecture_id and l.user_id = auth.uid()) and exists (select 1 from public.quizzes q where q.id = quiz_id and q.lecture_id = lecture_id));
