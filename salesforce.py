import json
import re
from datetime import datetime
import streamlit as st
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from base import chave


def sessao():
    try:
        c = st.secrets['salesforce']
        envelope = (
            '<env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">'
            '<env:Body><login xmlns="urn:partner.soap.sforce.com">'
            f'<username>{escape(c["USER"])}</username>'
            f'<password>{escape(c["PASSWORD"] + c.get("TOKEN", ""))}</password>'
            '</login></env:Body></env:Envelope>'
        )
        req = Request('https://login.salesforce.com/services/Soap/u/59.0', envelope.encode(),
                      {'Content-Type': 'text/xml;charset=UTF-8', 'SOAPAction': 'login'})
        with urlopen(req, timeout=20) as response:
            login = ElementTree.fromstring(response.read())
        host = 'https://' + urlsplit(login.findtext('.//{*}serverUrl')).netloc
        headers = {'Authorization': 'Bearer ' + login.findtext('.//{*}sessionId')}
        return host, headers
    except (OSError, ValueError, KeyError, TypeError, ElementTree.ParseError):
        raise ValueError('Não foi possível autenticar no Salesforce.') from None


def consultar(conexao, soql):
    host, headers = conexao
    try:
        caminho = '/services/data/v59.0/query?' + urlencode({'q': soql})
        while caminho:
            with urlopen(Request(host + caminho, headers=headers), timeout=30) as response:
                pagina = json.load(response)
            yield from pagina['records']
            caminho = pagina.get('nextRecordsUrl')
    except (OSError, ValueError, KeyError, TypeError, ElementTree.ParseError):
        raise ValueError('Não foi possível consultar o Salesforce. Confira a conexão e a configuração da integração.') from None


def grupos(valores):
    valores = sorted(set(valores))
    for inicio in range(0, len(valores), 180):
        yield "'" + "','".join(valores[inicio:inicio + 180]) + "'"


def cpf(valor):
    return re.sub(r'\D', '', valor or '')


def oportunidades():
    conexao = sessao()
    registros = list(consultar(conexao,
        'SELECT Id,CreatedDate,AccountId,Account.CPF__c,Account.Name,Account.TelefoneCelular__c,'
        'Account.PersonMobilePhone,Account.Phone,Telefone_Principal__c,Telefone__c,'
        'Empreendimento__r.Name,Empreendimento__r.CreatedDate FROM Opportunity '
        "WHERE StageName = 'Cancelado' AND AccountId != null AND Empreendimento__r.Regional__c = 'RJ' "
        "AND Empreendimento__r.UnidadeDeNegocio__c = 'Direcional' ORDER BY CreatedDate DESC, Id"))
    documentos = {cpf((r.get('Account') or {}).get('CPF__c')) for r in registros}
    documentos = {n for n in documentos if len(n) == 11 and len(set(n)) > 1}
    variantes = documentos | {f'{n[:3]}.{n[3:6]}.{n[6:9]}-{n[9:]}' for n in documentos}
    ids_bloqueados, cpfs_bloqueados = set(), set()
    for ids in grupos(r['AccountId'] for r in registros):
        for r in consultar(conexao, "SELECT AccountId,Account.CPF__c FROM Opportunity WHERE StageName != 'Cancelado' AND AccountId IN (" + ids + ")"):
            ids_bloqueados.add(r['AccountId'])
            cpfs_bloqueados.add(cpf((r.get('Account') or {}).get('CPF__c')))
    for valores in grupos(variantes):
        for r in consultar(conexao, "SELECT Account.CPF__c FROM Opportunity WHERE StageName != 'Cancelado' AND Account.CPF__c IN (" + valores + ")"):
            cpfs_bloqueados.add(cpf(r['Account']['CPF__c']))
    elegiveis = documentos - cpfs_bloqueados
    for r in registros:
        documento = cpf((r.get('Account') or {}).get('CPF__c'))
        if r['AccountId'] not in ids_bloqueados and documento in elegiveis:
            yield r


def carregar_leads():
    regioes = {chave(n): r for n, r in st.secrets.get('regioes_empreendimentos', {}).items()}
    for item in oportunidades():
        conta = item.get('Account') or {}
        nome = conta.get('Name')
        telefone = next((v for v in (item.get('Telefone_Principal__c'), conta.get('TelefoneCelular__c'),
                                      conta.get('PersonMobilePhone'), conta.get('Phone'),
                                      item.get('Telefone__c')) if v and v.strip()), '')
        telefone = re.sub(r'\D', '', telefone)
        if len(telefone) in (12, 13) and telefone.startswith('55'):
            telefone = telefone[2:]
        if not nome or not chave(nome) or len(telefone) not in (10, 11) or len(set(telefone)) == 1:
            continue
        projeto = item['Empreendimento__r']
        empreendimento = projeto['Name']
        try:
            empreendimento = empreendimento.encode('latin1').decode('utf-8')
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
        data = datetime.fromisoformat(projeto['CreatedDate']).astimezone(ZoneInfo('America/Sao_Paulo'))
        yield (nome, telefone, empreendimento, regioes.get(chave(empreendimento), 'Localização não confirmada'),
               data.date().isoformat(), item['CreatedDate'], item['Id'], item['AccountId'],
               cpf(conta.get('CPF__c')))


def acompanhar_envios(envios):
    por_id = {r['oportunidade_id']: r for r in envios if r['oportunidade_id'] and r['enviado_em']}
    if not por_id:
        return []
    conexao = sessao()
    saida = {id_: {'Solicitante': por_id[id_]['coordenador'], 'Fase atual': 'Sem acesso', 'Saiu de Cancelado': False,
                   'Nova avaliação': False, 'Novo agendamento': False, 'Visita realizada': False}
             for id_ in por_id}
    for ids in grupos(por_id):
        for r in consultar(conexao, f'SELECT Id,StageName FROM Opportunity WHERE Id IN ({ids})'):
            saida[r['Id']]['Fase atual'] = r['StageName']
            saida[r['Id']]['Saiu de Cancelado'] = r['StageName'] != 'Cancelado'
        consultas = (
            ('OpportunityHistory', 'OpportunityId', 'Saiu de Cancelado', " AND StageName != 'Cancelado'"),
            ('Avaliacao_credito__c', 'Oportunidade__c', 'Nova avaliação', ''),
            ('Event', 'WhatId', 'Novo agendamento', ' AND (DataAgendamento__c != null OR Data_da_Visita__c != null)'),
            ('Event', 'WhatId', 'Visita realizada', ' AND VisitaRealizada__c = true'),
        )
        for objeto, campo, indicador, filtro in consultas:
            for r in consultar(conexao, f'SELECT {campo},CreatedDate FROM {objeto} WHERE {campo} IN ({ids}){filtro}'):
                id_ = r[campo]
                if datetime.fromisoformat(r['CreatedDate']) > datetime.fromisoformat(por_id[id_]['enviado_em']):
                    saida[id_][indicador] = True
    return list(saida.values())
