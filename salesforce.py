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


def oportunidades():
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
        soql = (
            'SELECT Id,CreatedDate,Account.Name,Account.TelefoneCelular__c,Account.PersonMobilePhone,'
            'Account.Phone,Telefone_Principal__c,Telefone__c,Empreendimento__r.Name,'
            'Empreendimento__r.CreatedDate FROM Opportunity '
            "WHERE StageName = 'Cancelado' AND Empreendimento__r.Regional__c = 'RJ' "
            "AND Empreendimento__r.UnidadeDeNegocio__c = 'Direcional' ORDER BY CreatedDate DESC, Id"
        )
        caminho = '/services/data/v59.0/query?' + urlencode({'q': soql})
        while caminho:
            with urlopen(Request(host + caminho, headers=headers), timeout=30) as response:
                pagina = json.load(response)
            yield from pagina['records']
            caminho = pagina.get('nextRecordsUrl')
    except (OSError, ValueError, KeyError, TypeError, ElementTree.ParseError):
        raise ValueError('Não foi possível consultar o Salesforce. Confira a conexão e a configuração da integração.') from None


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
               data.date().isoformat(), item['CreatedDate'])
