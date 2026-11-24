import json
import os
import re
import sys
from base64 import b64decode
from collections import Counter
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from secrets import compare_digest, token_urlsafe

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from banco import aprovar, disponiveis, listar, pedido, solicitar
from base import REGIOES, SOLICITANTES
from indicadores import indicadores

QUANTIDADES = (*range(50, 501, 50), 750, 1000, 1250, 1500, 1750, 2000)


def catalogo():
    estoque = disponiveis('regiao,empreendimento')
    contagem = Counter((r['regiao'], r['empreendimento']) for r in estoque)
    return dict(regioes=REGIOES, solicitantes=SOLICITANTES, quantidades=QUANTIDADES,
                projetos=[dict(regiao=r, nome=p, total=n) for (r, p), n in sorted(contagem.items())])


class handler(BaseHTTPRequestHandler):
    def responder(self, dados, status=200, arquivo=False):
        corpo = dados if arquivo else json.dumps(dados, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                         if arquivo else 'application/json; charset=utf-8')
        if arquivo:
            self.send_header('Content-Disposition', 'attachment; filename="leads.xlsx"')
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        try:
            self.responder(catalogo())
        except ValueError as erro:
            self.responder({'erro': str(erro)}, 503)

    def do_POST(self):
        try:
            tamanho = int(self.headers.get('Content-Length', 0))
            if not 0 < tamanho <= 16384:
                raise ValueError('Solicitação inválida.')
            dados = json.loads(self.rfile.read(tamanho))
            if not isinstance(dados, dict):
                raise ValueError('Solicitação inválida.')
            acao = dados.get('acao')
            if acao == 'solicitar':
                self.novo_pedido(dados)
                return
            if acao in ('status', 'baixar'):
                self.consultar_pedido(dados, acao)
                return
            senha = os.environ.get('ADMIN_PASSWORD', '')
            if not senha or not compare_digest(senha.encode(), self.headers.get('X-Admin-Password', '').encode()):
                self.responder({'erro': 'Acesso administrativo inválido.'}, 401)
                return
            if acao == 'pedidos':
                self.responder(listar('distribuidor_pedidos', 'codigo,nome,quantidade,total,criado_em',
                                      order='criado_em.desc,codigo.asc'))
            elif acao == 'aprovar':
                nome, total = aprovar(self.codigo(dados))
                self.responder(dict(nome=nome, total=total))
            elif acao == 'indicadores':
                self.responder(indicadores())
            else:
                self.responder({'erro': 'Ação inválida.'}, 400)
        except (ValueError, KeyError, TypeError) as erro:
            self.responder({'erro': str(erro) if isinstance(erro, ValueError) else 'Solicitação inválida.'}, 400)

    @staticmethod
    def codigo(dados):
        codigo = str(dados.get('codigo', '')).strip().upper()
        if not re.fullmatch(r'[0-9A-F]{10}', codigo):
            raise ValueError('Informe o código de 10 caracteres.')
        return codigo

    def novo_pedido(self, dados):
        quantidade = dados.get('quantidade')
        regioes = dados.get('regioes')
        projetos = dados.get('empreendimentos')
        if quantidade not in QUANTIDADES or not isinstance(regioes, list) or not isinstance(projetos, list):
            raise ValueError('Confira a quantidade e os filtros do pedido.')
        opcoes = catalogo()['projetos']
        validos = {p['nome'] for p in opcoes if not regioes or p['regiao'] in regioes}
        if any(r not in REGIOES for r in regioes) or any(p not in validos for p in projetos) or not validos:
            raise ValueError('Selecione filtros com leads disponíveis.')
        sessao = token_urlsafe(32)
        codigo = solicitar(sessao, dados.get('nome'), quantidade, regioes, projetos)
        self.responder(dict(codigo=codigo, sessao=sessao), 201)

    def consultar_pedido(self, dados, acao):
        sessao = str(dados.get('sessao', ''))
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}', sessao):
            raise ValueError('Sessão do pedido inválida.')
        registro = pedido(self.codigo(dados), sessao)
        if not registro:
            self.responder({'erro': 'Pedido não encontrado.'}, 404)
        elif acao == 'status':
            self.responder({'total': registro['total']})
        elif registro['total'] is not None and registro['arquivo']:
            self.responder(b64decode(registro['arquivo']), arquivo=True)
        else:
            self.responder({'erro': 'O download aguarda aprovação.'}, 409)
