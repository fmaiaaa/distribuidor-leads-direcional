from base64 import b64encode, b64decode
from pathlib import Path
from secrets import compare_digest, token_urlsafe

import streamlit as st

from base import REGIOES
from banco import aprovar, listar, pedido, solicitar
from salesforce import carregar_leads

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
            entrar = st.form_submit_button('Entrar', type='primary')
        if entrar:
            if compare_digest(senha.encode(), senha_admin.encode()):
                st.session_state.admin_autenticado = True
                st.rerun()
            st.error('Senha incorreta.')
        st.stop()
    with st.form('aprovar'):
        codigo = st.text_input('Código do pedido', max_chars=10)
        liberar = st.form_submit_button('Liberar download', type='primary')
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

with st.form('pedido'):
    nome = st.text_input('Escreva o seu nome', max_chars=120)
    quantidade = st.selectbox('Quantos leads precisa?', QUANTIDADES)
    regioes = st.multiselect('Regiões', REGIOES, placeholder='Selecione uma ou mais regiões')
    st.caption('Deixe vazio para pegar de todas as regiões.')
    try:
        projetos = sorted(st.secrets.get('regioes_empreendimentos', {}))
    except OSError:
        projetos = []
    empreendimentos = st.multiselect('Empreendimentos', projetos, placeholder='Selecione um ou mais empreendimentos')
    st.caption('Deixe vazio para incluir todos os empreendimentos.')
    enviar = st.form_submit_button('Solicitar leads', type='primary', width='stretch')

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
