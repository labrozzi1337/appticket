create extension if not exists pgcrypto with schema extensions;
create schema if not exists appticket;
-- Após executar, adicione "appticket" em Project Settings > Data API > Exposed schemas.

create table if not exists appticket.usuarios (
  id uuid primary key default gen_random_uuid(),
  usuario text not null unique,
  ativo boolean not null default true,
  criado_em timestamptz not null default now()
);

create table if not exists appticket.senhas (
  usuario_id uuid primary key references appticket.usuarios(id) on delete cascade,
  hash_senha text not null,
  atualizado_em timestamptz not null default now()
);

alter table appticket.usuarios enable row level security;
alter table appticket.senhas enable row level security;

revoke all on appticket.usuarios from public, anon, authenticated;
revoke all on appticket.senhas from public, anon, authenticated;
grant usage on schema appticket to anon, authenticated, service_role;

create or replace function appticket.autenticar_usuario(p_usuario text, p_senha text)
returns boolean
language sql
stable
security definer
set search_path = appticket, extensions, pg_temp
as $$
  select exists (
    select 1
      from appticket.usuarios u
      join appticket.senhas s on s.usuario_id = u.id
     where u.usuario = p_usuario
       and u.ativo
       and s.hash_senha = crypt(p_senha, s.hash_senha)
  );
$$;

revoke all on function appticket.autenticar_usuario(text, text) from public;
grant execute on function appticket.autenticar_usuario(text, text) to anon, authenticated;
