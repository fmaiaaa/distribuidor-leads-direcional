create or replace view public.distribuidor_controle with (security_invoker = true) as
select b.*, r.coordenador as enviado_para, r.enviado_em,
       r.codigo as codigo_solicitacao,
       case when r.telefone is null then 'Disponível' else 'Enviado' end as situacao
from public.distribuidor_base b
left join public.distribuidor_retiradas r
on r.conta_id = b.conta_id or r.cpf_hash = b.cpf_hash
or r.telefone = b.telefone or r.nome_normalizado = b.nome_normalizado;
revoke all on public.distribuidor_controle from public, anon, authenticated;
grant select on public.distribuidor_controle to service_role;
