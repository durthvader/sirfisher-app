-- =====================================================================
-- Materializa fluxo_caixa_diario para eliminar o timeout do caixa.html
-- =====================================================================
--
-- PROBLEMA
--   painel_fluxo_caixa (via fluxo_caixa_diario) leva ~3,16 s. O role
--   `anon` tem statement_timeout = 3 s, entao a consulta estoura o limite
--   e o front (caixa.html) da throw nela, derrubando a pagina inteira em
--   ~80% das aberturas. A causa nao e volume de dados (as tabelas tem
--   dezenas de linhas), e sim a pilha de views nao materializadas: o
--   Postgres "inlina" e recalcula fato_financeiro ~17x, o calendario 13x
--   e projecao_venda_diaria 2x numa unica consulta (plano de 477 nos).
--
-- SOLUCAO
--   Materializar fluxo_caixa_diario num snapshot (mv_fluxo_caixa_diario) e
--   apontar painel_fluxo_caixa para esse snapshot. A logica pesada continua
--   viva na view fluxo_caixa_diario, mas so roda no REFRESH (fora do caminho
--   da requisicao). A leitura da pagina passa a ser um scan trivial (~ms).
--   O REFRESH e disparado por refresh_painel(), chamada ao fim das
--   importacoes (scripts em scripts/importacao/*.py).
--
-- OBJETOS AFETADOS
--   + mv_fluxo_caixa_diario   (novo materialized view)
--   ~ painel_fluxo_caixa      (passa a ler o snapshot; mesmas colunas)
--   + refresh_painel()        (nova funcao)
--   fluxo_caixa_diario NAO muda; e o unico consumidor dele era
--   painel_fluxo_caixa (repontado aqui), entao nada mais e impactado.
--
-- RISCO: baixo.
--   - Colunas de painel_fluxo_caixa sao identicas -> create or replace ok.
--   - Sem ciclo: o snapshot le fluxo_caixa_diario (real); nada le o snapshot
--     alem de painel_fluxo_caixa.
--   - Frescura: os dados do fluxo passam a refletir a ultima importacao
--     (que e quando de fato mudam). Entre importacoes, a curva de projecao
--     nao "anda" com o calendario. Aceitavel; se quiser diaria, adicionar
--     um job pg_cron chamando refresh_painel().
-- =====================================================================

-- 1. Snapshot materializado da view pesada (com dados).
create materialized view if not exists mv_fluxo_caixa_diario as
  select * from fluxo_caixa_diario
with data;

-- Indice unico (1 linha por dia) exigido por REFRESH ... CONCURRENTLY,
-- que atualiza o snapshot sem bloquear as leituras da pagina.
create unique index if not exists mv_fluxo_caixa_diario_dia_idx
  on mv_fluxo_caixa_diario (dia);

-- 2. Reaponta o painel para o snapshot (mesma projecao/colunas de antes).
create or replace view painel_fluxo_caixa as
  select
    dia,
    tipo,
    saldo,
    case when tipo = 'real'      then saldo else null::numeric end as saldo_real,
    case when tipo = 'projetado' then saldo else null::numeric end as saldo_projetado,
    entrada_projetada,
    saida_projetada,
    resultado_dia
  from mv_fluxo_caixa_diario
  order by dia;

-- 3. Leitura do snapshot pelos roles do PostgREST.
grant select on mv_fluxo_caixa_diario to anon, authenticated;

-- 4. Funcao de refresh, chamada pelos scripts de importacao ao fim da carga.
--    security definer: garante o refresh mesmo que o role da carga nao seja
--    dono do MV. statement_timeout = 0: o refresh (~3 s) nunca e cortado.
create or replace function refresh_painel()
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  set local statement_timeout = 0;
  refresh materialized view concurrently mv_fluxo_caixa_diario;
end;
$$;

grant execute on function refresh_painel() to service_role, authenticated;
