import json
import os
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree
from xml.sax.saxutils import escape


def sessao():
    try:
        usuario = escape(os.environ['SALESFORCE_USER'])
        senha = escape(os.environ['SALESFORCE_PASSWORD'] + os.getenv('SALESFORCE_TOKEN', ''))
        corpo = (
            '<env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">'
            '<env:Body><login xmlns="urn:partner.soap.sforce.com">'
            f'<username>{usuario}</username><password>{senha}</password>'
            '</login></env:Body></env:Envelope>'
        )
        dominio = os.getenv('SALESFORCE_DOMAIN', 'direcional.my')
        if not dominio.replace('.', '').replace('-', '').isalnum():
            raise ValueError()
        req = Request(f'https://{dominio}.salesforce.com/services/Soap/u/59.0', corpo.encode(),
                      {'Content-Type': 'text/xml;charset=UTF-8', 'SOAPAction': 'login'})
        with urlopen(req, timeout=15) as resposta:
            login = ElementTree.fromstring(resposta.read())
        host = urlsplit(login.findtext('.//{*}serverUrl')).netloc
        token = login.findtext('.//{*}sessionId')
        if not host or not token:
            raise ValueError()
        return 'https://' + host, {'Authorization': 'Bearer ' + token}
    except (OSError, ValueError, KeyError, TypeError, ElementTree.ParseError):
        raise ValueError('A conexão Salesforce do painel está indisponível.') from None


def requisitar(conexao, caminho, corpo=None):
    host, headers = conexao
    try:
        req = Request(host + caminho, None if corpo is None else json.dumps(corpo).encode(),
                      dict(headers, **{'Content-Type': 'application/json'}))
        with urlopen(req, timeout=20) as resposta:
            return json.load(resposta)
    except (OSError, ValueError):
        raise ValueError('O Salesforce não retornou todos os dados do painel.') from None


def consultar(conexao, soql):
    caminho = '/services/data/v59.0/query?' + urlencode({'q': soql})
    while caminho:
        pagina = requisitar(conexao, caminho)
        yield from pagina['records']
        caminho = pagina.get('nextRecordsUrl')


def grupos(valores):
    valores = sorted(set(valores))
    for inicio in range(0, len(valores), 150):
        yield "'" + "','".join(valores[inicio:inicio + 150]) + "'"
