-- Planpause: Datenbankschema für Supabase.
-- Einmal im Supabase-Dashboard unter "SQL Editor" ausführen.
--
-- Alles liegt im eigenen Schema "planpause" und im eigenen Bucket "planpause",
-- ohne Verknüpfung zu anderen Tabellen im Projekt (einzige Ausnahme: auth.users
-- für die Anmeldung). Umzug später: pg_dump --schema=planpause + Bucket kopieren.
--
-- Zugriff hat nur die API (Rolle service_role). anon/authenticated bekommen keine
-- Rechte, RLS ist zusätzlich an: Mit dem öffentlichen Schlüssel im Browser lässt
-- sich weder lesen noch schreiben.
--
-- Danach: Project Settings → Data API → "Exposed schemas" um "planpause" ergänzen.

create schema if not exists planpause;

create table if not exists planpause.orgs (
  id         text primary key check (id ~ '^[a-z0-9][a-z0-9_-]{2,63}$'),
  name       text not null,
  created_at timestamptz not null default now()
);

create table if not exists planpause.org_members (
  user_id    uuid primary key references auth.users (id) on delete cascade,
  org_id     text not null references planpause.orgs (id) on delete cascade,
  created_at timestamptz not null default now()
);

create table if not exists planpause.projects (
  id         text primary key,
  org_id     text not null references planpause.orgs (id) on delete cascade,
  meta       jsonb not null,
  created_at timestamptz not null default now()
);
create index if not exists projects_org_idx on planpause.projects (org_id);

alter table planpause.orgs        enable row level security;
alter table planpause.org_members enable row level security;
alter table planpause.projects    enable row level security;

revoke all on schema planpause from anon, authenticated;
grant usage on schema planpause to service_role;
grant all on all tables in schema planpause to service_role;
alter default privileges in schema planpause grant all on tables to service_role;

-- Privater Speicher für Fotos und Ergebnisse (max. 25 MB pro Datei)
insert into storage.buckets (id, name, public, file_size_limit)
values ('planpause', 'planpause', false, 26214400)
on conflict (id) do nothing;

-- Selbst-Registrierung (Oktober 2026): kostenlose Grundrisse eines Probe-Betriebs.
-- null = ohne Begrenzung (eingeladene und zahlende Betriebe), Zahl = verbleibende kostenlose Analysen.
alter table planpause.orgs add column if not exists trial_left integer;
