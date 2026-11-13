# Distribuidor de leads Direcional RJ

No Streamlit Community Cloud, selecione este repositório, a branch main e o arquivo app.py. Em Settings > Secrets, mantenha a seção [salesforce] existente e acrescente [supabase] e [admin] conforme secrets.example.toml. Use a chave secreta de servidor do projeto Integrações Salesforce. 

O banco Supabase guarda solicitações, atribuições e os arquivos aprovados. A migração incluída prepara o banco. O app consulta oportunidades no Salesforce quando o administrador aprova o código.

Para habilitar os filtros por empreendimento e região, adicione a seção `[regioes_empreendimentos]` nos Secrets. Use uma linha por empreendimento no formato `"Nome cadastrado no Salesforce" = "Zona Norte"`. Com a seção vazia, o pedido sem filtros continua disponível.

Após a aprovação, o botão Baixar Excel aparece para o solicitante, que deve manter a aba aberta até baixar. O painel administrativo é acessível pelo botão Entrar como admin.
