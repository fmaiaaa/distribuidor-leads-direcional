import os
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from banco import listar
from base import SOLICITANTES, chave
from salesforce import consultar, grupos, sessao, requisitar

IMOB = {
    'Daniel': ('DANIEL TEIXEIRA CARVALHO', ['005KZ000000tLCTYA2', '0053Z00000L4gvyQAB', '005KZ000000tLD2YAM']),
    'João Paulo': ('JOÃO COSTA PAULO DA CONCEIÇÃO', ['005U600000t98bUIAQ']),
    'Lucas Pinho': ('LUCAS HENRIQUE DANTAS DE PINHO', ['005U600000vpFp2IAE']),
    'Andreza': ('ANDREZA DE BARROS MELO RABELO', ['005U600000vfwbxIAA']),
    'Henrique Delaroli': ('HENRIQUE DELAROLI GIL', ['005TT00000ZR83lYAD']),
    'Paulo Victor': ('PAULO VICTOR DE JESUS SILVEIRA', ['005TT00000WRGawYAH']),
    'Yasmin': ('Yasmin Ribeiro de Lucena de Almeida', ['005TT00000YRbuLYAT']),
    'Lemos': ('LUIZ CARLOS DE SOUZA LEMOS', ['0053Z00000KmZSZQA3', '005f100000HD1MWAA1', '005KZ000000tLCsYAM']),
}
COMERCIAL = {
    'Dutra': ('FELIPE DUTRA OLIVEIRA', ['005f100000HBT6ZAAX'], 'Gerente_regional__c'),
    'Leo': ('LEONARDO JULIANO GUEDES', [], 'Gerente_regional__c'),
    'Marvin': ('MARVIN LIMA VASCONCELLOS CICERO', [], 'Gerente_regional__c'),
    'Daniel': ('DANIEL DA SILVEIRA ALVES', ['0053Z00000KhwCOQAZ'], 'Gerente_de_vendas__c'),
    'Luciano': ('LUCIANO CARLOS DOS SANTOS PIRES', ['0053Z00000MJ3owQAD'], 'Gerente_regional__c'),
}
FUSO = ZoneInfo('America/Sao_Paulo')
REPORT = '/services/data/v59.0/analytics/reports/00O3Z000005ZsPmUAK'


def mapa(conexao):
    mapeados = {'Imob - ' + nome: (completo, ids, 'Gerente_de_vendas__c')
                for nome, (completo, ids) in IMOB.items()}
    for apelido, (nome, conhecidos, campo) in COMERCIAL.items():
        configurados = os.getenv('SF_COORD_' + apelido.upper(), '')
        ids = configurados.replace(' ', '').split(',') if configurados else conhecidos
        ids = [i for i in ids if re.fullmatch(r'005[a-zA-Z0-9]{12}(?:[a-zA-Z0-9]{3})?', i)]
        if ids:
            usuarios = [u for grupo in grupos(ids) for u in consultar(conexao,
                        f'SELECT Id,Name FROM User WHERE Id IN ({grupo})')]
        else:
            usuarios = list(consultar(conexao, f"SELECT Id,Name FROM User WHERE Name = '{nome}'"))
            if len(usuarios) != 1:
                continue
        nomes = {chave(u['Name']) for u in usuarios}
        if len(nomes) == 1 and (configurados or nomes == {chave(nome)}):
            mapeados['Coordenador Comercial - ' + apelido] = (
                usuarios[0]['Name'], [u['Id'] for u in usuarios], campo)
    return mapeados


def vendas(conexao, inicio, fim, meta=None):
    coluna_id = 'Opportunity.IDOportunidade__c'
    coluna_data = 'Opportunity.ContratoGeradoEm__c'
    if meta is None:
        meta = requisitar(conexao, REPORT + '/describe')['reportMetadata']
    filtro = meta['standardDateFilter']
    if filtro['column'] != coluna_data:
        raise ValueError('A data de referência do relatório Patrick mudou.')
    colunas = list(dict.fromkeys(meta['detailColumns'] + [coluna_id, coluna_data]))
    periodo = dict(meta, detailColumns=colunas, standardDateFilter=dict(
        filtro, durationValue='CUSTOM', startDate=inicio.isoformat(), endDate=fim.isoformat()))
    resultado = requisitar(conexao, REPORT + '?includeDetails=true', {'reportMetadata': periodo})
    linhas = resultado['factMap']['T!T'].get('rows', [])
    if not resultado.get('allData'):
        if inicio == fim:
            raise ValueError('O relatório Patrick excedeu o limite diário de registros.')
        meio = inicio + (fim - inicio) // 2
        return vendas(conexao, inicio, meio, meta) | vendas(conexao, meio + timedelta(days=1), fim, meta)
    return {(str(r['dataCells'][colunas.index(coluna_id)]['value']),
             date.fromisoformat(str(r['dataCells'][colunas.index(coluna_data)]['value'])[:10]))
            for r in linhas}


def indicadores():
    aprovados = {p['codigo'] for p in listar('distribuidor_pedidos', 'codigo,total',
                                           order='codigo.asc') if p['total'] is not None}
    linhas = [r for r in listar('distribuidor_retiradas',
              'codigo,coordenador,dados,telefone,oportunidade_id,conta_id,enviado_em',
              order='telefone.asc') if r['codigo'] in aprovados]
    grupos_site = {n: dict(nome=n, enviados=0, retomados=None, pastas=None,
                           aprovadas=None, vendas=None) for n in SOLICITANTES}
    for r in linhas:
        if r['coordenador'] in grupos_site:
            grupos_site[r['coordenador']]['enviados'] += 1
    detalhes = [dict(solicitante=r['coordenador'], nome=(r['dados'] or [''])[0],
                     telefone=r['telefone'], oportunidade=r['oportunidade_id']) for r in linhas]
    rastreaveis = [r for r in linhas if r['enviado_em'] and r['conta_id'] and r['oportunidade_id']]
    if not rastreaveis:
        return dict(grupos=list(grupos_site.values()), leads=detalhes,
                    mapa={'Imob - ' + k: v[0] for k, v in IMOB.items()},
                    aviso='Ainda não há leads liberados com vínculo rastreável.')
    conexao = sessao()
    mapeados = mapa(conexao)
    for nome in mapeados:
        grupos_site[nome].update(retomados=0, pastas=0, aprovadas=0, vendas=0)
    por_conta = {r['conta_id']: r for r in rastreaveis if r['coordenador'] in mapeados}
    inicio = min(datetime.fromisoformat(r['enviado_em']) for r in rastreaveis)
    limite = inicio.isoformat().replace('+00:00', 'Z')
    desde = inicio.astimezone(FUSO).date()
    hoje = datetime.now(FUSO).date()
    retomados = set()
    oportunidades = {}

    def depois(data, lead):
        envio = datetime.fromisoformat(lead['enviado_em'])
        if not data:
            return False
        if len(data) == 10:
            return envio.astimezone(FUSO).date() < date.fromisoformat(data) <= hoje
        return datetime.fromisoformat(data) > envio

    def autor(r, lead):
        return r['CreatedById'] in mapeados[lead['coordenador']][1]

    for ids in grupos(por_conta):
        for r in consultar(conexao, 'SELECT Id,AccountId,CreatedById,CreatedDate,IDOportunidade__c,'
                           f'Gerente_de_vendas__c,Gerente_regional__c FROM Opportunity WHERE AccountId IN ({ids})'):
            lead = por_conta[r['AccountId']]
            oportunidades[r['Id']] = (r, lead)
            if autor(r, lead) and depois(r['CreatedDate'], lead):
                retomados.add(lead['oportunidade_id'])
        for objeto in ('Task', 'Event'):
            for r in consultar(conexao, f'SELECT AccountId,CreatedById,CreatedDate FROM {objeto} '
                               f'WHERE AccountId IN ({ids}) AND CreatedDate > {limite}'):
                lead = por_conta[r['AccountId']]
                if autor(r, lead) and depois(r['CreatedDate'], lead):
                    retomados.add(lead['oportunidade_id'])
    codigos = {str(r['IDOportunidade__c']): (r, l) for r, l in oportunidades.values()
               if r.get('IDOportunidade__c')}
    for codigo, data in (vendas(conexao, desde, hoje) if codigos else ()):
        if codigo in codigos:
            r, lead = codigos[codigo]
            nome = lead['coordenador']
            completo, _, campo = mapeados[nome]
            if chave(r.get(campo)) == chave(completo) and depois(data.isoformat(), lead):
                grupos_site[nome]['vendas'] += 1
    for ids in grupos(oportunidades):
        for r in consultar(conexao, 'SELECT OpportunityId,CreatedById,CreatedDate,OldValue,NewValue '
                           f"FROM OpportunityFieldHistory WHERE OpportunityId IN ({ids}) AND Field = 'StageName' "
                           f'AND CreatedDate > {limite}'):
            _, lead = oportunidades[r['OpportunityId']]
            if (r['OldValue'] == 'Cancelado' and r['NewValue'] not in ('Cancelado', 'Fechado e perdido')
                    and r['NewValue'] and autor(r, lead) and depois(r['CreatedDate'], lead)):
                retomados.add(lead['oportunidade_id'])
        for r in consultar(conexao, 'SELECT Oportunidade__c,CreatedById,CreatedDate,dataAprovacaoSAFI__c '
                           f'FROM Avaliacao_credito__c WHERE Oportunidade__c IN ({ids}) '
                           "AND Empreendimento__r.Regional__c = 'RJ' AND Empreendimento__r.UnidadeDeNegocio__c = 'Direcional' "
                           f'AND (CreatedDate > {limite} OR dataAprovacaoSAFI__c >= {desde.isoformat()})'):
            _, lead = oportunidades[r['Oportunidade__c']]
            nome = lead['coordenador']
            if not autor(r, lead):
                continue
            if depois(r['CreatedDate'], lead):
                grupos_site[nome]['pastas'] += 1
                retomados.add(lead['oportunidade_id'])
            if depois(r['CreatedDate'], lead) and depois(r['dataAprovacaoSAFI__c'], lead):
                grupos_site[nome]['aprovadas'] += 1
                retomados.add(lead['oportunidade_id'])
    for r in rastreaveis:
        if r['oportunidade_id'] in retomados:
            grupos_site[r['coordenador']]['retomados'] += 1
    return dict(grupos=list(grupos_site.values()), leads=detalhes,
                mapa={k: v[0] for k, v in mapeados.items()},
                aviso='— indica atribuição pendente. Datas sem horário contam a partir do dia seguinte à liberação.')
