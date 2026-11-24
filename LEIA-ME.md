# Distribuidor de leads Direcional RJ

## Site Vercel
Importe este repositório na Vercel e configure Root Directory como web. O vercel.json define a saída public e a API fica em api/leads.py.
Configure SUPABASE_URL, SUPABASE_SECRET_KEY e ADMIN_PASSWORD em Production.
O painel Salesforce também usa SALESFORCE_USER, SALESFORCE_PASSWORD, SALESFORCE_TOKEN e SALESFORCE_DOMAIN (direcional.my por padrão).
SF_COORD_LEO e SF_COORD_MARVIN permitem informar User.Id para desambiguar cadastros.
As credenciais ficam nas variáveis do servidor.

## Banco e carga
Aplique as migrações de supabase/migrations em ordem, somente as ainda pendentes.
distribuidor_base contém nome, telefone, oportunidade, conta, identificador protegido de CPF, empreendimento, região e datas de criação.
distribuidor_retiradas preserva permanentemente destinatário, data/hora, pedido e identificação do cliente.
distribuidor_disponiveis exclui qualquer cliente já enviado por conta, CPF protegido, telefone ou nome.
distribuidor_controle reúne a base com os campos enviado_para, enviado_em, codigo_solicitacao e situacao.

Instale requirements.txt com python -m pip install -r requirements.txt.
Configure .streamlit/secrets.toml conforme secrets.example.toml, preservando a mesma IDENTITY_KEY em todas as cargas.
Execute python atualizar_base.py. O arquivo Atualizar base de leads.bat faz a carga e registra a tarefa semanal.
O corte usa CreatedDate da oportunidade até o fim do dia de três meses antes, no fuso America/Sao_Paulo.
São selecionadas oportunidades Cancelado, de empreendimentos RJ e Direcional. Clientes podem ter outras oportunidades não canceladas. Nome, telefone, conta e CPF são deduplicados.
empreendimentos.csv guarda o mapeamento das regiões. A seção regioes_empreendimentos nos secrets pode complementar o cadastro.

## Administração
Pedidos precisam de aprovação para liberar o Excel. A atribuição é gravada em transação e a unicidade impede enviar o mesmo cliente novamente.
O painel inclui leads enviados, contatos retomados, pastas, pastas aprovadas e vendas. As ações posteriores são cruzadas com a conta e as oportunidades, usando os usuários dos coordenadores.
A referência de vendas é o relatório Salesforce 00O3Z000005ZsPmUAK, a mesma do painel Patrick.
Datas Salesforce sem horário são consideradas a partir do dia seguinte à liberação, evitando atribuir ações anteriores do mesmo dia.
Os gráficos exibem atribuição pendente quando o usuário Salesforce ainda não foi resolvido.

## Streamlit
app.py continua sendo a entrada do Streamlit e usa secrets.example.toml.
