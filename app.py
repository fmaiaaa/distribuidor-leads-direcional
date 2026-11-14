from base64 import b64encode, b64decode
from pathlib import Path
from secrets import compare_digest, token_urlsafe

import streamlit as st

from base import REGIOES, SOLICITANTES, chave
from banco import aprovar, listar, pedido, solicitar
from salesforce import acompanhar_envios, carregar_leads, consultar, sessao
from collections import Counter

QUANTIDADES = (50, 100, 150, 200, 250, 300, 350, 400, 450, 500,
               750, 1000, 1250, 1500, 1750, 2000)

assets = Path(__file__).resolve().parent / 'assets'
st.set_page_config(page_title='Retirada de leads', page_icon=str(assets / 'icone.png'))


def imagem(nome, tipo):
    dados = b64encode((assets / nome).read_bytes()).decode('ascii')
    return f'data:image/{tipo};base64,{dados}'


admin = st.query_params.get('painel') == 'admin' or st.session_state.get('abrir_admin', False)
estilo = (assets / 'ficha.css').read_text(encoding='utf-8')
estilo = estilo.replace('__FUNDO__', imagem('fundo.jpg', 'jpeg'))
st.html(f'<style>{estilo}</style>')
st.html(
    '<header class="ficha-hero">'
    f'<img src="{imagem("logo.png", "png")}" alt="Direcional">'
    + ('<h1>Painel administrativo</h1>' if admin else '<h1>Retirada de leads</h1>')
    +
    '</header><div class="ficha-hero-bar" aria-hidden="true"></div>'
)


if admin:
    if st.button('Voltar ao formulário', width='stretch'):
        st.session_state.pop('abrir_admin', None)
        st.session_state.pop('admin_autenticado', None)
        st.query_params.pop('painel', None)
        st.rerun()
    try:
        senha_admin = st.secrets['admin']['PASSWORD']
    except (OSError, KeyError):
        senha_admin = ''
    if not senha_admin:
        st.error('Configure a senha administrativa conforme o LEIA-ME.')
        st.stop()
    if not st.session_state.get('admin_autenticado'):
        with st.form('login'):
            senha = st.text_input('Senha administrativa', type='password')
            entrar = st.form_submit_button('Entrar', type='primary', width='stretch')
        if entrar:
            if compare_digest(senha.encode(), senha_admin.encode()):
                st.session_state.admin_autenticado = True
                st.rerun()
            st.error('Senha incorreta.')
        st.stop()
    with st.form('aprovar'):
        codigo = st.text_input('Código do pedido', max_chars=10)
        liberar = st.form_submit_button('Liberar download', type='primary', width='stretch')
    if liberar:
        try:
            with st.spinner('Consultando oportunidades no Salesforce…'):
                nome, total = aprovar(codigo.strip().upper(), carregar_leads)
            st.success(f'Download liberado para {nome} com {total} leads.')
        except ValueError as exc:
            st.error(str(exc))
    try:
        pedidos = listar('distribuidor_pedidos', 'codigo,nome,quantidade,regioes,empreendimentos,total',
                        order='criado_em.desc,codigo.asc')
    except ValueError as exc:
        st.error(str(exc))
        st.stop()
    if pedidos:
        st.subheader('Solicitações')
        st.dataframe([
            {'Código': p['codigo'], 'Solicitante': p['nome'], 'Quantidade': p['quantidade'],
             'Regiões': ', '.join(p['regioes']) or 'Todas',
             'Empreendimentos': ', '.join(p['empreendimentos']) or 'Todos',
             'Situação': 'Pendente' if p['total'] is None else f"Liberado · {p['total']} leads"}
            for p in pedidos
        ], hide_index=True)
    else:
        st.info('Ainda não há solicitações.')
    st.subheader('Resultados da distribuição')
    por_pessoa = Counter()
    por_canal = Counter()
    for p in pedidos:
        if p['total'] is None:
            continue
        por_pessoa[p['nome']] += p['total']
        canal = p['nome'].split(' - ', 1)[0] if p['nome'] in SOLICITANTES else 'Histórico'
        por_canal[canal] += p['total']
    if por_pessoa:
        st.dataframe([{'Solicitante': n, 'Leads enviados': q} for n, q in por_pessoa.most_common()], hide_index=True)
        st.dataframe([{'Canal': n, 'Leads enviados': q} for n, q in por_canal.most_common()], hide_index=True)
    if st.button('Consultar resultados no Salesforce', width='stretch'):
        try:
            with st.spinner('Consultando fases, avaliações e visitas…'):
                envios = listar('distribuidor_retiradas', 'oportunidade_id,enviado_em,coordenador', order='telefone.asc')
                resultados = acompanhar_envios(envios)
            st.session_state.resultados_leads = resultados
            st.session_state.envios_sem_vinculo = len(envios) - len(resultados)
        except ValueError as exc:
            st.error(str(exc))
    if 'resultados_leads' in st.session_state:
        resultados = st.session_state.resultados_leads
        st.caption(f"{len(resultados)} oportunidades acompanhadas · {st.session_state.envios_sem_vinculo} envios antigos sem vínculo.")
        if resultados:
            fases = Counter(r['Fase atual'] for r in resultados)
            st.dataframe([{'Fase atual': f, 'Oportunidades': q} for f, q in fases.most_common()], hide_index=True)
            indicadores = ('Saiu de Cancelado', 'Nova avaliação', 'Novo agendamento', 'Visita realizada')
            for indicador in indicadores:
                st.metric(indicador, sum(r[indicador] for r in resultados))
            canais = {}
            for r in resultados:
                nome = r['Solicitante']
                canal = nome.split(' - ', 1)[0] if nome in SOLICITANTES else 'Histórico'
                contagem = canais.setdefault(canal, Counter())
                contagem['Oportunidades'] += 1
                for indicador in indicadores:
                    contagem[indicador] += r[indicador]
            st.dataframe([{'Canal': canal, **contagem} for canal, contagem in canais.items()], hide_index=True)
    st.stop()


@st.dialog('Código da solicitação')
def mostrar_codigo(codigo):
    st.write('Envie este código ao administrador para liberar o download.')
    st.code(codigo, language=None)


@st.fragment(run_every=3)
def acompanhar(codigos, sessao):
    try:
        for codigo in reversed(codigos):
            p = pedido(codigo, sessao)
            if p is None:
                continue
            quantidade, total = p['quantidade'], p['total']
            if total is None:
                st.info(f'Pedido {codigo} · Aguardando aprovação.')
                continue
            arquivo = b64decode(p['arquivo'])
            st.success(f'Pedido {codigo} · {total} de {quantidade} leads liberados.')
            st.download_button('Baixar Excel', arquivo, f'leads-{codigo}.xlsx',
                               'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                               key=f'baixar-{codigo}', on_click='ignore')
    except ValueError as exc:
        st.error(str(exc))


if 'sessao_pedidos' not in st.session_state:
    st.session_state.sessao_pedidos = token_urlsafe(32)
    st.session_state.codigos = []

@st.cache_data(ttl=600, show_spinner=False)
def listar_empreendimentos():
    registros = consultar(
        sessao(),
        "SELECT Name FROM Empreendimento__c WHERE Regional__c = 'RJ' "
        "AND UnidadeDeNegocio__c = 'Direcional' AND Id IN "
        "(SELECT Empreendimento__c FROM Opportunity WHERE StageName = 'Cancelado')",
    )
    nomes = set()
    for registro in registros:
        nome = registro['Name']
        try:
            nome = nome.encode('latin1').decode('utf-8')
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
        nomes.add(nome)
    return sorted(nomes, key=str.casefold)


try:
    mapa_projetos = st.secrets.get('regioes_empreendimentos', {})
except OSError:
    mapa_projetos = {}
regiao_por_projeto = {chave(nome): regiao for nome, regiao in mapa_projetos.items()}

try:
    projetos = listar_empreendimentos()
    aviso_projetos = None if projetos else 'Nenhum empreendimento encontrado para a consulta atual.'
except ValueError:
    projetos = sorted(mapa_projetos)
    aviso_projetos = ('Salesforce temporariamente indisponível. Exibindo os empreendimentos configurados.'
                      if projetos else 'Não foi possível carregar os empreendimentos do Salesforce.')

with st.container(border=True):
    nome = st.selectbox('Selecione seu nome', SOLICITANTES, index=None, placeholder='Selecione o solicitante')
    quantidade = st.selectbox('Quantos leads precisa?', QUANTIDADES)
    if not regiao_por_projeto:
        st.session_state.regioes_pedido = []
    regioes = st.multiselect(
        'Regiões', REGIOES, placeholder='Selecione uma ou mais regiões',
        key='regioes_pedido', disabled=not regiao_por_projeto,
    )
    if regiao_por_projeto:
        st.caption('Deixe vazio para pegar de todas as regiões.')
    else:
        st.caption('Filtro de região indisponível até configurar o mapeamento de empreendimentos.')

    opcoes = [projeto for projeto in projetos
              if not regioes or regiao_por_projeto.get(chave(projeto)) in regioes]
    selecao = st.session_state.get('empreendimentos_pedido', [])
    selecionados = [projeto for projeto in selecao if projeto in opcoes]
    if selecionados != selecao:
        st.session_state.empreendimentos_pedido = selecionados
    if aviso_projetos:
        st.caption(aviso_projetos)
    empreendimentos = st.multiselect(
        'Empreendimentos', opcoes, placeholder='Selecione um ou mais empreendimentos',
        key='empreendimentos_pedido', disabled=not opcoes,
    )
    if regioes and not opcoes:
        st.caption('Nenhum empreendimento disponível nas regiões selecionadas.')
    else:
        st.caption('Deixe vazio para incluir todos os empreendimentos disponíveis.')
    enviar = st.button(
        'Solicitar leads', type='primary', width='stretch',
        disabled=bool(regioes and not opcoes),
    )

if st.button('Entrar como admin', key='entrar_admin', width='stretch'):
    st.session_state.abrir_admin = True
    st.rerun()

if enviar:
    try:
        codigo = solicitar(st.session_state.sessao_pedidos, nome, quantidade, regioes, empreendimentos)
        st.session_state.codigos.append(codigo)
        mostrar_codigo(codigo)
    except ValueError as exc:
        st.error(str(exc))

if st.session_state.codigos:
    acompanhar(st.session_state.codigos, st.session_state.sessao_pedidos)
