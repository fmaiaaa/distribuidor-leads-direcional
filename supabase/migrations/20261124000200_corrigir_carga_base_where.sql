create or replace function public.distribuidor_atualizar_base(p_leads jsonb)
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
