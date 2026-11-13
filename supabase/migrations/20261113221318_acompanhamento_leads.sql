alter table public.distribuidor_retiradas
 add column oportunidade_id text,
 add column conta_id text unique,
 add column cpf_hash text unique,
 add column enviado_em timestamptz;
create index distribuidor_retiradas_codigo_idx on public.distribuidor_retiradas(codigo);

create or replace function public.distribuidor_aprovar(p_codigo text,p_linhas jsonb,p_arquivo text)
returns integer language plpgsql security invoker set search_path = '' as $$
declare v_pedido public.distribuidor_pedidos%rowtype;
begin
 select * into strict v_pedido from public.distribuidor_pedidos where codigo=p_codigo for update;
 if v_pedido.total is not null then return v_pedido.total; end if;
 insert into public.distribuidor_retiradas
 (telefone,nome_normalizado,codigo,coordenador,data,dados,oportunidade_id,conta_id,cpf_hash,enviado_em)
 select x.telefone,x.nome_normalizado,p_codigo,v_pedido.nome,(now() at time zone 'America/Sao_Paulo')::date,
 x.dados,x.oportunidade_id,x.conta_id,x.cpf_hash,now()
 from jsonb_to_recordset(p_linhas) as x(telefone text,nome_normalizado text,dados jsonb,oportunidade_id text,conta_id text,cpf_hash text)
 where x.oportunidade_id is not null and x.conta_id is not null and x.cpf_hash is not null
 order by x.telefone;
 if (select count(*) from public.distribuidor_retiradas where codigo=p_codigo) <> jsonb_array_length(p_linhas) then
   raise exception 'Identificação incompleta no lote';
 end if;
 update public.distribuidor_pedidos set total=jsonb_array_length(p_linhas),arquivo=p_arquivo where codigo=p_codigo;
 return jsonb_array_length(p_linhas);
end;
$$;
