import json
import secrets
import hmac
from base64 import b64encode
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import streamlit as st

from base import SOLICITANTES, chave, datas, espacados, excel


def api(recurso, filtros=None, corpo=None):
    try:
        config = st.secrets['supabase']
        chave_api = config['SECRET_KEY']
        url = config['URL'].rstrip('/') + '/rest/v1/' + recurso
        if filtros:
            url += '?' + urlencode(filtros)
        headers = {'apikey': chave_api, 'Content-Type': 'application/json'}
        if not chave_api.startswith('sb_secret_'):
            headers['Authorization'] = 'Bearer ' + chave_api
        req = Request(url, None if corpo is None else json.dumps(corpo).encode(), headers)
        with urlopen(req, timeout=35) as resp:
            dados = resp.read()
            return json.loads(dados) if dados else None
    except HTTPError as exc:
        if exc.code == 409:
            raise ValueError('Outro pedido usou parte desse lote. Tente aprovar novamente.') from None
        raise ValueError('Não foi possível acessar o Supabase. Confira os Secrets e a configuração do banco.') from None
    except (URLError, OSError, KeyError):
        raise ValueError('Configure o Supabase nos Secrets do Streamlit.') from None


def listar(tabela, campos, **filtros):
    linhas = []
    for offset in range(0, 1000000, 500):
        pagina = api(tabela, {'select': campos, 'limit': 500, 'offset': offset, **filtros})
        linhas.extend(pagina)
        if len(pagina) < 500:
            return linhas
    raise ValueError('Limite de consulta ao histórico atingido.')


def solicitar(sessao, nome, quantidade, regioes, empreendimentos):
    if nome not in SOLICITANTES:
        raise ValueError('Selecione o nome do solicitante.')
    codigo = secrets.token_hex(5).upper()
    api('distribuidor_pedidos', corpo=dict(codigo=codigo, sessao=sessao, nome=nome,
        quantidade=quantidade, regioes=regioes, empreendimentos=empreendimentos))
    return codigo


def pedido(codigo, sessao=None):
    filtro = {'codigo': 'eq.' + codigo}
    if sessao is not None:
        filtro['sessao'] = 'eq.' + sessao
    rows = api('distribuidor_pedidos', filtro)
    return rows[0] if rows else None


def aprovar(codigo, carregar):
    p = pedido(codigo)
    if not p:
        raise ValueError('Código não encontrado.')
    if p['total'] is not None:
        return p['nome'], p['total']
    try:
        segredo = st.secrets['supabase']['IDENTITY_KEY'].encode()
    except (OSError, KeyError):
        raise ValueError('Configure IDENTITY_KEY nos Secrets antes de aprovar pedidos.') from None
    if len(segredo) < 32:
        raise ValueError('IDENTITY_KEY precisa ter ao menos 32 caracteres.')
    historico = listar('distribuidor_retiradas', 'telefone,nome_normalizado,conta_id,cpf_hash', order='telefone.asc')
    nomes = {r['nome_normalizado'] for r in historico}
    telefones = {r['telefone'] for r in historico}
    contas = {r['conta_id'] for r in historico}
    documentos = {r['cpf_hash'] for r in historico}
    candidatos = []
    for r in carregar():
        n, t, e, regiao, _, criada, oportunidade, conta, documento = r
        normal = chave(n)
        cpf_hash = hmac.digest(segredo, documento.encode(), 'sha256').hex()
        if not oportunidade or not conta or not documento or normal in nomes or t in telefones or conta in contas or cpf_hash in documentos:
            continue
        nomes.add(normal)
        telefones.add(t)
        contas.add(conta)
        documentos.add(cpf_hash)
        if (not p['regioes'] or regiao in p['regioes']) and (not p['empreendimentos'] or e in p['empreendimentos']):
            candidatos.append((n, t, e, regiao, r[4], oportunidade, conta, cpf_hash, criada))
    if not candidatos:
        raise ValueError('Não há leads disponíveis para esse pedido.')
    candidatos.sort(key=lambda r: r[-1])
    selecionados = espacados(candidatos, p['quantidade'])
    hoje = datetime.now(ZoneInfo('America/Sao_Paulo')).date().isoformat()
    arquivo = excel(datas((n,t,p['nome'],hoje,e,r,cr)) for n,t,e,r,cr,*_ in selecionados)
    linhas = [{'telefone': r[1], 'nome_normalizado': chave(r[0]), 'dados': r[:5],
               'oportunidade_id': r[5], 'conta_id': r[6], 'cpf_hash': r[7]} for r in selecionados]
    total = api('rpc/distribuidor_aprovar', corpo={'p_codigo': codigo, 'p_linhas': linhas,
                'p_arquivo': b64encode(arquivo).decode('ascii')})
    return p['nome'], total
