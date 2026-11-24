create table public.distribuidor_base (
 oportunidade_id text primary key, conta_id text not null, cpf_hash text not null,
 nome text not null, nome_normalizado text not null, telefone text not null,
 empreendimento text not null, regiao text not null, criacao_empreendimento date not null,
 criacao_oportunidade timestamptz not null
);
alter table public.distribuidor_base enable row level security;
revoke all on public.distribuidor_base from public, anon, authenticated;
grant select, insert, delete on public.distribuidor_base to service_role;

create view public.distribuidor_disponiveis with (security_invoker = true) as
 select b.* from public.distribuidor_base b
 where not exists (select 1 from public.distribuidor_retiradas r
 where r.conta_id=b.conta_id or r.cpf_hash=b.cpf_hash
 or r.telefone=b.telefone or r.nome_normalizado=b.nome_normalizado);
revoke all on public.distribuidor_disponiveis from public, anon, authenticated;
grant select on public.distribuidor_disponiveis to service_role;

create function public.distribuidor_atualizar_base(p_leads jsonb)
returns integer language plpgsql security invoker set search_path = '' as $$
begin
 lock table public.distribuidor_base in share row exclusive mode;
 delete from public.distribuidor_base where true;
 insert into public.distribuidor_base
 select * from jsonb_populate_recordset(null::public.distribuidor_base, p_leads);
 return jsonb_array_length(p_leads);
end;
$$;
revoke all on function public.distribuidor_atualizar_base(jsonb) from public, anon, authenticated;
grant execute on function public.distribuidor_atualizar_base(jsonb) to service_role;
