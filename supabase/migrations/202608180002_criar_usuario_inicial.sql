-- EDITE os dois valores abaixo antes de executar esta migration.
insert into appticket.usuarios (usuario)
values ('SUBSTITUA_USUARIO')
on conflict (usuario) do update set ativo = true;

insert into appticket.senhas (usuario_id, hash_senha)
select id, extensions.crypt('SUBSTITUA_SENHA', extensions.gen_salt('bf'))
  from appticket.usuarios
 where usuario = 'SUBSTITUA_USUARIO'
on conflict (usuario_id) do update
set hash_senha = excluded.hash_senha,
    atualizado_em = now();
