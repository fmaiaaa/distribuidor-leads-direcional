from bisect import bisect_left
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from unicodedata import normalize

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

PASTA = Path(__file__).resolve().parent
COLUNAS = ('Nome do Cliente', 'Telefone do Cliente', 'Coordenador/Gerente',
           'Data', 'Empreendimento', 'Região', 'Data de criação do empreendimento')
REGIOES = ('Zona Norte', 'Zona Leste', 'Jacarepaguá/Barra', 'Zona Oeste', 'Baixada/Nova Iguaçu')


def chave(texto):
    return ' '.join(normalize('NFKD', texto).encode('ascii', 'ignore').decode().casefold().split())


def excel(linhas):
    livro = Workbook()
    aba = livro.active
    aba.title = 'Leads'
    aba.append(COLUNAS)
    for celula in aba[1]:
        celula.fill = PatternFill('solid', fgColor='123D68')
        celula.font = Font(color='FFFFFF', bold=True)
    for linha in linhas:
        aba.append(linha)
        for celula in aba[aba.max_row]:
            if isinstance(celula.value, str):
                celula.data_type = 's'
            if isinstance(celula.value, date):
                celula.number_format = 'dd/mm/yyyy'
    for letra, largura in zip('ABCDEFG', (44, 23, 30, 15, 44, 29, 39)):
        aba.column_dimensions[letra].width = largura
    aba.freeze_panes = 'A2'
    aba.auto_filter.ref = aba.dimensions
    buffer = BytesIO()
    livro.save(buffer)
    return buffer.getvalue()


def datas(linha):
    n, t, c, d, e, r, cr = linha
    return n, t, c, date.fromisoformat(d) if d else None, e, r, date.fromisoformat(cr)


def espacados(registros, quantidade):
    if quantidade >= len(registros):
        return registros
    datas = [datetime.fromisoformat(r[-1]).timestamp() for r in registros]
    intervalo = datas[-1] - datas[0]
    selecionados = []
    anterior = -1
    for i in range(quantidade):
        fracao = i / (quantidade - 1) if quantidade > 1 else .5
        minimo = anterior + 1
        maximo = len(registros) - quantidade + i
        alvo = datas[0] + intervalo * fracao
        if intervalo:
            posicao = min(maximo, bisect_left(datas, alvo, minimo, maximo + 1))
            if posicao > minimo and alvo - datas[posicao - 1] < abs(datas[posicao] - alvo):
                posicao -= 1
        else:
            posicao = round((len(registros) - 1) * fracao)
        selecionados.append(registros[posicao])
        anterior = posicao
    return selecionados



