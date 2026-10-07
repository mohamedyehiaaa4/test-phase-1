-- Planning App schema (Supabase Postgres). Run once on an empty database.
--
-- Model: every PM approval of a step is one row in step_versions. The step's items live in their own tables and
-- belong to that version. A change makes a new version; old versions stay as history. Links between steps point
-- at the rows of the version that was current when the later step was saved.
--
-- The app talks to it with two functions that use the same JSON shape as the agents' drafts:
--   save_step(project, step, approved_by, summary, draft) -> new version number (one transaction)
--   load_step(project, step) -> draft JSON of the current version, or null
--   load_project(project) -> every current step at once: {step: {version, summary, draft}}

-- ============================================================================================================
-- 1. Tables
-- ============================================================================================================
create schema if not exists langgraph;  -- LangGraph checkpoints (graph progress); not exposed to the Data API

create table public.users (
  id         uuid primary key default gen_random_uuid(),
  name       text not null,
  created_at timestamptz not null default now()
);

create table public.projects (
  id         uuid primary key default gen_random_uuid(),
  name       text not null,
  pm_id      uuid not null references public.users (id),
  created_at timestamptz not null default now()
);
create index projects_pm_id_idx on public.projects (pm_id);

create table public.step_versions (
  id          bigint generated always as identity primary key,
  project_id  uuid not null references public.projects (id) on delete cascade,
  step        text not null check (step in ('discovery', 'requirements', 'stories', 'criteria')),
  version     int  not null check (version > 0),
  summary     text not null,  -- short summary handed to later steps
  approved_by uuid not null references public.users (id),
  approved_at timestamptz not null default now(),
  unique (project_id, step, version)
);
create index step_versions_approved_by_idx on public.step_versions (approved_by);

-- discovery
create table public.discovery_summaries (
  version_id  bigint primary key references public.step_versions (id) on delete cascade,
  title       text not null,
  summary     text not null,
  assumptions text[] not null default '{}'
);

-- requirements
create table public.prds (
  version_id bigint primary key references public.step_versions (id) on delete cascade,
  title      text not null,
  body       text not null
);

create table public.requirements (
  id              bigint generated always as identity primary key,
  version_id      bigint not null references public.step_versions (id) on delete cascade,
  key             text not null,
  kind            text not null check (kind in ('functional', 'non_functional')),
  category        text not null default '',
  title           text not null,
  description     text not null,
  priority        text not null check (priority in ('high', 'medium', 'low')),
  priority_reason text not null,
  basis           text not null default '',
  unique (version_id, key)
);

create table public.assumptions (
  id         bigint generated always as identity primary key,
  version_id bigint not null references public.step_versions (id) on delete cascade,
  key        text not null,
  statement  text not null,
  reason     text not null,
  unique (version_id, key)
);

-- stories
create table public.stories (
  id              bigint generated always as identity primary key,
  version_id      bigint not null references public.step_versions (id) on delete cascade,
  key             text not null,
  title           text not null,
  statement       text not null,
  points          numeric check (points >= 0),
  priority        text not null check (priority in ('high', 'medium', 'low')),
  priority_reason text not null,
  unique (version_id, key)
);

create table public.story_requirements (
  story_id       bigint not null references public.stories (id) on delete cascade,
  requirement_id bigint not null references public.requirements (id) on delete cascade,
  primary key (story_id, requirement_id)
);
create index story_requirements_requirement_id_idx on public.story_requirements (requirement_id);

-- criteria
create table public.criteria (
  id         bigint generated always as identity primary key,
  version_id bigint not null references public.step_versions (id) on delete cascade,
  key        text not null,
  story_id   bigint not null references public.stories (id) on delete cascade,
  scenario   text not null,
  type       text not null check (type in ('happy_path', 'negative', 'edge_case')),
  given_steps text[] not null default '{}',
  when_step  text not null,
  then_steps text[] not null check (cardinality(then_steps) > 0),
  unique (version_id, key)
);
create index criteria_story_id_idx on public.criteria (story_id);

-- The current (latest) version of each step
create view public.current_steps with (security_invoker = true) as
select distinct on (project_id, step) id, project_id, step, version, summary, approved_by, approved_at
from public.step_versions
order by project_id, step, version desc;

-- ============================================================================================================
-- 2. Save and load
-- ============================================================================================================
create or replace function public.current_version_id(p_project uuid, p_step text)
returns bigint language sql stable set search_path = '' as $$
  select id from public.current_steps where project_id = p_project and step = p_step
$$;

create or replace function public.save_step(
  p_project uuid, p_step text, p_by uuid, p_summary text, p_draft jsonb)
returns int language plpgsql set search_path = '' as $$
declare
  v_version int;
  v_id      bigint;
  v_up      bigint;  -- current version of the step this one links to
  v_missing text;
begin
  if not exists (select 1 from public.projects where id = p_project and pm_id = p_by) then
    raise exception 'only the project manager of this project can approve its work';
  end if;

  select coalesce(max(version), 0) + 1 into v_version
  from public.step_versions where project_id = p_project and step = p_step;
  insert into public.step_versions (project_id, step, version, summary, approved_by)
  values (p_project, p_step, v_version, p_summary, p_by) returning id into v_id;

  if p_step = 'discovery' then
    insert into public.discovery_summaries (version_id, title, summary, assumptions)
    select v_id, d->>'title', d->>'summary',
           array(select jsonb_array_elements_text(coalesce(d->'assumptions', '[]')))
    from (select p_draft->'summary' as d) s;

  elsif p_step = 'requirements' then
    insert into public.prds (version_id, title, body)
    values (v_id, p_draft->'prd'->>'title', p_draft->'prd'->>'body');
    insert into public.requirements (version_id, key, kind, category, title, description, priority, priority_reason, basis)
    select v_id, r->>'key', r->>'kind', coalesce(r->>'category', ''), r->>'title', r->>'description',
           r->>'priority', r->>'priority_reason', coalesce(r->>'basis', '')
    from jsonb_array_elements(p_draft->'requirements') r;
    insert into public.assumptions (version_id, key, statement, reason)
    select v_id, a->>'key', a->>'statement', a->>'reason'
    from jsonb_array_elements(coalesce(p_draft->'assumptions', '[]')) a;

  elsif p_step = 'stories' then
    v_up := public.current_version_id(p_project, 'requirements');
    insert into public.stories (version_id, key, title, statement, points, priority, priority_reason)
    select v_id, s->>'key', s->>'title', s->>'statement', (s->>'points')::numeric, s->>'priority', s->>'priority_reason'
    from jsonb_array_elements(p_draft->'stories') s;
    select string_agg(k, ', ') into v_missing
    from jsonb_array_elements(p_draft->'stories') s, jsonb_array_elements_text(s->'requirement_keys') k
    where not exists (select 1 from public.requirements where version_id = v_up and key = k);
    if v_missing is not null then raise exception 'unknown requirement keys: %', v_missing; end if;
    insert into public.story_requirements (story_id, requirement_id)
    select st.id, r.id
    from jsonb_array_elements(p_draft->'stories') s
    join public.stories st on st.version_id = v_id and st.key = s->>'key'
    cross join jsonb_array_elements_text(s->'requirement_keys') k
    join public.requirements r on r.version_id = v_up and r.key = k;

  elsif p_step = 'criteria' then
    v_up := public.current_version_id(p_project, 'stories');
    select string_agg(c->>'story_key', ', ') into v_missing
    from jsonb_array_elements(p_draft->'criteria') c
    where not exists (select 1 from public.stories where version_id = v_up and key = c->>'story_key');
    if v_missing is not null then raise exception 'unknown story keys: %', v_missing; end if;
    insert into public.criteria (version_id, key, story_id, scenario, type, given_steps, when_step, then_steps)
    select v_id, c->>'key', st.id, c->>'scenario', c->>'type',
           array(select jsonb_array_elements_text(coalesce(c->'given', '[]'))), c->>'when',
           array(select jsonb_array_elements_text(c->'then'))
    from jsonb_array_elements(p_draft->'criteria') c
    join public.stories st on st.version_id = v_up and st.key = c->>'story_key';

  else
    raise exception 'unknown step %', p_step;
  end if;

  return v_version;
end $$;

create or replace function public.load_step(p_project uuid, p_step text)
returns jsonb language plpgsql stable set search_path = '' as $$
declare
  v bigint := public.current_version_id(p_project, p_step);
begin
  if v is null then return null; end if;

  if p_step = 'discovery' then
    return (select jsonb_build_object('summary', jsonb_build_object(
              'title', title, 'summary', summary, 'assumptions', to_jsonb(assumptions)))
            from public.discovery_summaries where version_id = v);

  elsif p_step = 'requirements' then
    return jsonb_build_object(
      'prd', (select jsonb_build_object('title', title, 'body', body) from public.prds where version_id = v),
      'requirements', coalesce((select jsonb_agg(jsonb_build_object(
          'key', key, 'kind', kind, 'category', category, 'title', title, 'description', description,
          'priority', priority, 'priority_reason', priority_reason, 'basis', basis) order by id)
        from public.requirements where version_id = v), '[]'),
      'assumptions', coalesce((select jsonb_agg(jsonb_build_object(
          'key', key, 'statement', statement, 'reason', reason) order by id)
        from public.assumptions where version_id = v), '[]'));

  elsif p_step = 'stories' then
    return jsonb_build_object('stories', coalesce((select jsonb_agg(jsonb_build_object(
        'key', s.key, 'title', s.title, 'statement', s.statement, 'points', s.points, 'priority', s.priority,
        'priority_reason', s.priority_reason,
        'requirement_keys', coalesce((select jsonb_agg(r.key order by r.id) from public.story_requirements sr
                                      join public.requirements r on r.id = sr.requirement_id
                                      where sr.story_id = s.id), '[]')) order by s.id)
      from public.stories s where s.version_id = v), '[]'));

  elsif p_step = 'criteria' then
    return jsonb_build_object('criteria', coalesce((select jsonb_agg(jsonb_build_object(
        'key', c.key, 'story_key', st.key, 'scenario', c.scenario, 'type', c.type,
        'given', to_jsonb(c.given_steps), 'when', c.when_step, 'then', to_jsonb(c.then_steps)) order by c.id)
      from public.criteria c join public.stories st on st.id = c.story_id where c.version_id = v), '[]'));

  end if;
  raise exception 'unknown step %', p_step;
end $$;

-- Every current step of a project in one call (instead of one load_step call per step).
create or replace function public.load_project(p_project uuid)
returns jsonb language sql stable set search_path = '' as $$
  select coalesce(jsonb_object_agg(step, jsonb_build_object(
           'version', version, 'summary', summary,
           'draft', public.load_step(p_project, step))), '{}')
  from public.current_steps where project_id = p_project
$$;

-- ============================================================================================================
-- 3. Access: only the server (service_role key / direct connection) may touch any of this
-- ============================================================================================================
do $$
declare t text;
begin
  foreach t in array array['users', 'projects', 'step_versions', 'discovery_summaries', 'prds', 'requirements',
    'assumptions', 'stories', 'story_requirements', 'criteria'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('revoke all on public.%I from anon, authenticated', t);
  end loop;
end $$;
revoke all on public.current_steps from anon, authenticated;
revoke all on schema langgraph from anon, authenticated;
revoke execute on function public.current_version_id, public.save_step, public.load_step, public.load_project
  from public, anon, authenticated;
grant execute on function public.current_version_id, public.save_step, public.load_step, public.load_project
  to service_role;

-- ============================================================================================================
-- 4. Your project and its PM (use the PROJECT_ID and PM_USER_ID from .env)
-- ============================================================================================================
-- insert into public.users (id, name) values ('<PM_USER_ID>', 'Mohamed Yehia');
-- insert into public.projects (id, name, pm_id) values ('<PROJECT_ID>', 'RepoMind Phase 1', '<PM_USER_ID>');
