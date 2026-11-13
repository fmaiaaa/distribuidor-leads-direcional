create table public.distribuidor_pedidos (
 codigo text primary key, sessao text not null, nome text not null,
 quantidade integer not null check (quantidade between 1 and 2000),
 regioes jsonb not null, empreendimentos jsonb not null,
 criado_em timestamptz not null default now(),
 total integer, arquivo text
);
create table public.distribuidor_retiradas (
 telefone text primary key, nome_normalizado text not null unique,
 codigo text references public.distribuidor_pedidos(codigo),
 coordenador text not null, data date not null, dados jsonb not null
);
alter table public.distribuidor_pedidos enable row level security;
alter table public.distribuidor_retiradas enable row level security;
revoke all on public.distribuidor_pedidos, public.distribuidor_retiradas from public, anon, authenticated;
grant select, insert, update on public.distribuidor_pedidos, public.distribuidor_retiradas to service_role;

create function public.distribuidor_aprovar(p_codigo text,p_linhas jsonb,p_arquivo text)
returns integer language plpgsql security invoker set search_path = '' as $$
declare v_pedido public.distribuidor_pedidos%rowtype;
begin
 select * into strict v_pedido from public.distribuidor_pedidos where codigo=p_codigo for update;
 if v_pedido.total is not null then return v_pedido.total; end if;
 insert into public.distribuidor_retiradas (telefone,nome_normalizado,codigo,coordenador,data,dados)
 select x.telefone,x.nome_normalizado,p_codigo,v_pedido.nome,(now() at time zone 'America/Sao_Paulo')::date,x.dados
 from jsonb_to_recordset(p_linhas) as x(telefone text,nome_normalizado text,dados jsonb)
 order by x.telefone;
 update public.distribuidor_pedidos set total=jsonb_array_length(p_linhas),arquivo=p_arquivo where codigo=p_codigo;
 return jsonb_array_length(p_linhas);
end;
$$;
revoke all on function public.distribuidor_aprovar(text,jsonb,text) from public, anon, authenticated;
grant execute on function public.distribuidor_aprovar(text,jsonb,text) to service_role;
