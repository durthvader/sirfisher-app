# Sir Fisher App - Instruções para Claude Code

Este projeto é o painel financeiro do Sir Fisher.

## Estrutura

- Arquivos HTML principais ficam na raiz do projeto.
- A pasta `supabase/migrations/` contém migrations SQL que são aplicadas no Supabase via GitHub Integration.
- O arquivo `.mcp.json` configura acesso MCP ao Supabase em modo somente leitura.

## Regras importantes

1. Não alterar diretamente o banco pelo MCP.
2. Usar MCP apenas para leitura, análise de schema, tabelas, views e conferência de dados.
3. Qualquer alteração estrutural no banco deve ser feita criando uma migration SQL em `supabase/migrations/`.
4. Antes de criar uma migration, explicar:
   - qual problema será resolvido;
   - quais tabelas/views serão afetadas;
   - qual SQL será criado;
   - risco da alteração.
5. Nunca alterar chaves Supabase, URLs ou tokens sem autorização.
6. Antes de modificar HTML/CSS/JS, informar quais arquivos serão alterados.
7. Sempre preservar compatibilidade mobile.
8. Não quebrar as páginas existentes:
   - home.html
   - vendas.html
   - caixa.html
   - dre.html
   - classificar_excecoes.html
   - analise_individual.html
   - venda_especie.html

## Fluxo correto para banco

1. Consultar o schema via MCP em modo leitura.
2. Gerar migration SQL em `supabase/migrations/`.
3. O usuário revisa.
4. Fazer commit.
5. Fazer push para `main`.
6. Supabase aplica automaticamente.

## Fluxo correto para frontend

1. Ler o arquivo HTML atual.
2. Propor ajuste.
3. Alterar apenas os arquivos necessários.
4. Validar visualmente no navegador.
5. Commit e push.