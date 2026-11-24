import calendar
import hmac
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import streamlit as st

from banco import api, listar
from base import chave
from salesforce import carregar_leads


def atualizar():
    agora = datetime.now(ZoneInfo('America/Sao_Paulo'))
    ano, mes = divmod(agora.year * 12 + agora.month - 4, 12)
    mes += 1
    dia = min(agora.day, calendar.monthrange(ano, mes)[1])
    limite = agora.replace(year=ano, month=mes, day=dia, hour=23, minute=59,
                          second=59, microsecond=0)
    segundo_utc = limite.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    segredo = st.secrets['supabase']['IDENTITY_KEY'].encode()
    if len(segredo) < 32:
        raise ValueError('IDENTITY_KEY precisa ter ao menos 32 caracteres.')
    historico = listar('distribuidor_retiradas', 'telefone,nome_normalizado,conta_id,cpf_hash',
                       order='telefone.asc')
    nomes = {r['nome_normalizado'] for r in historico}
    telefones = {r['telefone'] for r in historico}
    contas = {r['conta_id'] for r in historico}
    documentos = {r['cpf_hash'] for r in historico}
    leads = []
    for nome, telefone, projeto, regiao, criado_projeto, criada, oportunidade, conta, cpf in carregar_leads(segundo_utc):
        normalizado = chave(nome)
        cpf_hash = hmac.digest(segredo, cpf.encode(), 'sha256').hex()
        if normalizado in nomes or telefone in telefones or conta in contas or cpf_hash in documentos:
            continue
        nomes.add(normalizado)
        telefones.add(telefone)
        contas.add(conta)
        documentos.add(cpf_hash)
        leads.append(dict(oportunidade_id=oportunidade, conta_id=conta, cpf_hash=cpf_hash, nome=nome,
                          nome_normalizado=normalizado, telefone=telefone, empreendimento=projeto,
                          regiao=regiao, criacao_empreendimento=criado_projeto, criacao_oportunidade=criada))
    total = api('rpc/distribuidor_atualizar_base', corpo={'p_leads': leads})
    print(f'Base atualizada. {total} leads elegíveis até {limite:%d/%m/%Y}.')


if __name__ == '__main__':
    try:
        atualizar()
    except (ValueError, OSError, KeyError) as erro:
        print(f'Falha ao atualizar a base. {erro}', file=sys.stderr)
        sys.exit(1)
