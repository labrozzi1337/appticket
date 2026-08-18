create schema if not exists appticket;

create table if not exists appticket.transacoes (
  id_transacao text primary key,
  id_presence text,
  nome text,
  cpf text,
  email text,
  telefone text,
  cargo text,
  tipo_ingresso text,
  qtde_tickets text,
  total text,
  liquido text,
  desconto text,
  pagamento text,
  status text,
  status_code text,
  status_api text,
  origem text,
  data text,
  erro text
);

create index if not exists transacoes_data_idx
  on appticket.transacoes (data desc);
create index if not exists transacoes_status_code_idx
  on appticket.transacoes (status_code);

alter table appticket.transacoes enable row level security;

revoke all on appticket.transacoes from public, anon, authenticated;
grant usage on schema appticket to service_role;
grant select, insert, update, delete on appticket.transacoes to service_role;

comment on table appticket.transacoes is
  'Dados coletados do AppTicket. A aplicacao acessa esta tabela somente pelo backend.';
