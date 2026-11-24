const el = id => document.getElementById(id);
let projetos = [];
let senha = '';
let retirada = JSON.parse(sessionStorage.getItem('retirada') || 'null');

async function api(dados, admin = false) {
    const resposta = await fetch('/api/leads', dados ? {
        method: 'POST',
        headers: {'Content-Type': 'application/json', ...(admin ? {'X-Admin-Password': senha} : {})},
        body: JSON.stringify(dados),
    } : {});
    if (resposta.ok && dados?.acao === 'baixar') return resposta.blob();
    const corpo = await resposta.json();
    if (!resposta.ok) throw new Error(corpo.erro || 'Não foi possível concluir a solicitação.');
    return corpo;
}

function selecionados(id) {
    return [...el(id).querySelectorAll('input:checked')].map(input => input.value);
}

function opcoes(id, nomes, contagens, manter = []) {
    el(id).replaceChildren(...nomes.map(nome => {
        const rotulo = document.createElement('label');
        const campo = document.createElement('input');
        campo.type = 'checkbox';
        campo.value = nome;
        campo.checked = manter.includes(nome);
        campo.disabled = !contagens[nome];
        rotulo.append(campo, document.createTextNode(`${nome} (${contagens[nome] || 0} disponíveis)`));
        return rotulo;
    }));
}

function contagens(linhas, campo) {
    const totais = Object.create(null);
    for (const linha of linhas) totais[linha[campo]] = (totais[linha[campo]] || 0) + linha.total;
    return totais;
}

function filtrar() {
    const regioes = selecionados('regioes');
    const totais = contagens(projetos.filter(p => !regioes.length || regioes.includes(p.regiao)), 'nome');
    opcoes('projetos', Object.keys(totais).sort((a, b) => a.localeCompare(b, 'pt-BR')), totais, selecionados('projetos'));
    el('solicitar').disabled = !Object.keys(totais).length;
}

async function atualizarStatus() {
    if (!retirada) return;
    try {
        const {total} = await api({acao: 'status', ...retirada});
        el('baixar').hidden = total === null;
        el('status').textContent = total === null ? `Pedido ${retirada.codigo} aguardando aprovação.` : `${total} leads liberados.`;
    } catch (erro) {
        el('status').textContent = erro.message;
    }
}

el('regioes').addEventListener('change', filtrar);
el('solicitacao').addEventListener('submit', async evento => {
    evento.preventDefault();
    el('solicitar').disabled = true;
    try {
        retirada = await api({acao: 'solicitar', nome: el('nome').value, quantidade: Number(el('quantidade').value),
            regioes: selecionados('regioes'), empreendimentos: selecionados('projetos')});
        sessionStorage.setItem('retirada', JSON.stringify(retirada));
        el('baixar').hidden = true;
        el('numero').textContent = retirada.codigo;
        el('codigo').showModal();
        await atualizarStatus();
    } catch (erro) {
        el('status').textContent = erro.message;
    } finally {
        el('solicitar').disabled = false;
    }
});

el('baixar').addEventListener('click', async () => {
    try {
        const arquivo = await api({acao: 'baixar', ...retirada});
        const url = URL.createObjectURL(arquivo);
        const link = document.createElement('a');
        link.href = url;
        link.download = `leads-${retirada.codigo}.xlsx`;
        link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (erro) {
        el('status').textContent = erro.message;
    }
});

function listar(id, textos) {
    el(id).replaceChildren(...textos.map(texto => {
        const item = document.createElement('li');
        item.textContent = texto;
        return item;
    }));
}

async function painel() {
    const pedidos = await api({acao: 'pedidos'}, true);
    listar('pedidos', pedidos.map(p => `${p.codigo} · ${p.nome} · ${p.total === null ? 'Pendente' : p.total + ' liberados'}`));
    const aprovados = pedidos.filter(p => p.total !== null);
    const porPessoa = contagens(aprovados, 'nome');
    const porCanal = contagens(aprovados.map(p => ({canal: p.nome.split(' - ')[0], total: p.total})), 'canal');
    listar('totais', [...Object.entries(porPessoa), ...Object.entries(porCanal)].map(([nome, total]) => `${nome} · ${total}`));
    el('entrar').hidden = true;
    el('painel').hidden = false;
}

el('abrir-admin').onclick = () => el('admin').showModal();
el('consultar-indicadores').onclick = async () => {
    const botao = el('consultar-indicadores');
    botao.disabled = true;
    el('status-admin').textContent = 'Consultando indicadores…';
    try {
        const dados = await api({acao: 'indicadores'}, true);
        if (!el('admin').open || !senha) return;
        const metricas = [
            ['enviados', 'Leads enviados'], ['retomados', 'Contatos retomados'],
            ['pastas', 'Pastas feitas'], ['aprovadas', 'Pastas aprovadas feitas'],
            ['vendas', 'Vendas feitas']
        ];
        el('indicadores').replaceChildren(...metricas.map(([chave, titulo]) => {
            const grafico = document.createElement('section');
            const cabecalho = document.createElement('h3');
            cabecalho.textContent = titulo;
            grafico.append(cabecalho);
            const maximo = Math.max(1, ...dados.grupos.map(g => g[chave] ?? 0));
            for (const grupo of dados.grupos) {
                const linha = document.createElement('div');
                linha.className = 'indicador-linha';
                const nome = document.createElement('span');
                nome.textContent = grupo.nome;
                const valor = document.createElement('span');
                valor.textContent = grupo[chave] ?? '—';
                linha.append(nome);
                if (grupo[chave] !== null) {
                    const barra = document.createElement('meter');
                    barra.max = maximo;
                    barra.value = grupo[chave];
                    barra.setAttribute('aria-label', grupo.nome);
                    linha.append(barra);
                } else {
                    linha.append(document.createElement('span'));
                }
                linha.append(valor);
                grafico.append(linha);
            }
            return grafico;
        }));
        listar('leads-enviados', dados.leads.map(l =>
            `${l.nome} · ${l.telefone} · ${l.solicitante}`));
        listar('mapa-coordenadores', dados.grupos.map(g =>
            `${g.nome} · ${dados.mapa[g.nome] ?? 'Vínculo Salesforce pendente'}`));
        el('status-admin').textContent = dados.aviso;
    } catch (erro) {
        if (el('admin').open) el('status-admin').textContent = erro.message;
    } finally {
        botao.disabled = false;
    }
};
el('admin').addEventListener('close', () => {
    senha = '';
    el('senha').value = '';
    el('entrar').hidden = false;
    el('painel').hidden = true;
    el('status-admin').textContent = '';
    el('indicadores').replaceChildren();
    el('leads-enviados').replaceChildren();
    el('mapa-coordenadores').replaceChildren();
});
el('entrar').onsubmit = async evento => {
    evento.preventDefault();
    senha = el('senha').value;
    try {
        await painel();
        el('status-admin').textContent = '';
    } catch (erro) {
        senha = '';
        el('status-admin').textContent = erro.message;
    }
};
el('aprovar').onsubmit = async evento => {
    evento.preventDefault();
    try {
        const {total} = await api({acao: 'aprovar', codigo: el('liberar').value}, true);
        el('status-admin').textContent = `${total} leads liberados.`;
        await painel();
    } catch (erro) {
        el('status-admin').textContent = erro.message;
    }
};

api().then(dados => {
    projetos = dados.projetos;
    el('nome').append(...dados.solicitantes.map(nome => new Option(nome, nome)));
    el('quantidade').append(...dados.quantidades.map(q => new Option(q, q)));
    opcoes('regioes', dados.regioes, contagens(projetos, 'regiao'));
    filtrar();
}).catch(erro => { el('status').textContent = erro.message; });
atualizarStatus();
setInterval(atualizarStatus, 5000);
