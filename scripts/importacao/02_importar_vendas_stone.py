#!/usr/bin/env python3
# =====================================================================
# SIR FISHER - ETAPA 1 - Arquivo 09
# Importador de VENDAS STONE
#
# O que faz:
#   1. le o CSV cru de vendas Stone
#   2. limpa datas e valores
#   3. deduplica por STONE ID
#   4. insere em raw_stone_vendas; o que ja existe e ignorado
#   5. recalcula automaticamente o saldo de fechamento mensal por seguranca
#
# Observacao:
#   Este arquivo impacta principalmente vendas/faturamento. O saldo de caixa
#   normalmente e mais afetado por extrato, BB e recebiveis. Mesmo assim, o
#   recalculo no fim e seguro e mantem a rotina padronizada.
#
# COMO RODAR:
#   Simulacao (nao toca no banco):
#       python 09_importar_vendas_stone.py vendas.csv --dry-run
#
#   De verdade (precisa do .env com DATABASE_URL):
#       python 09_importar_vendas_stone.py vendas.csv
#
# Reimportar o mesmo periodo e SEGURO: so entra o que ainda nao existe.
# =====================================================================

import sys
import csv
import re
from datetime import datetime


# ---- parsing de valores no formato brasileiro -----------------------
def parse_valor(s):
    if s is None:
        return None

    cleaned = re.sub(r'[^\d,.\-]', '', str(s))

    if cleaned in ('', '-', '.', ','):
        return None

    neg = cleaned.startswith('-')
    cleaned = cleaned.replace('.', '').replace(',', '.').lstrip('-')

    if cleaned == '':
        return None

    try:
        v = float(cleaned)
    except ValueError:
        return None

    return -v if neg else v


def parse_data(s):
    s = (s or '').strip()

    for fmt in ('%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M', '%d/%m/%Y'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue

    return None


def parse_int(s):
    s = (s or '').strip()

    try:
        return int(s)
    except ValueError:
        return None


def g(row, key):
    v = row.get(key)

    if v is None:
        return None

    v = str(v).strip()
    return v if v != '' else None


# ---- leitura e transformacao do CSV ---------------------------------
def ler_csv(caminho):
    registros = []

    with open(caminho, encoding='utf-8-sig', newline='') as fh:
        reader = csv.DictReader(fh, delimiter=';')

        for row in reader:
            stone_id = g(row, 'STONE ID')

            if not stone_id:
                continue  # linha sem STONE ID nao tem como deduplicar; ignora

            registros.append({
                'documento':            g(row, 'DOCUMENTO'),
                'stonecode':            g(row, 'STONECODE'),
                'data_venda':           parse_data(g(row, 'DATA DA VENDA')),
                'bandeira':             g(row, 'BANDEIRA'),
                'produto':              g(row, 'PRODUTO'),
                'stone_id':             stone_id,
                'n_parcelas':           parse_int(g(row, 'N DE PARCELAS')),
                'valor_bruto':          parse_valor(g(row, 'VALOR BRUTO')),
                'valor_liquido':        parse_valor(g(row, 'VALOR LIQUIDO')),
                'desconto_mdr':         parse_valor(g(row, 'DESCONTO DE MDR')),
                'desconto_antecipacao': parse_valor(g(row, 'DESCONTO DE ANTECIPACAO')),
                'desconto_unificado':   parse_valor(g(row, 'DESCONTO UNIFICADO')),
                'n_cartao':             g(row, 'N DO CARTAO'),
                'meio_captura':         g(row, 'MEIO DE CAPTURA'),
                'n_serie':              g(row, 'N DE SERIE'),
                'ultimo_status':        g(row, 'ULTIMO STATUS'),
                'data_ultimo_status':   parse_data(g(row, 'DATA DO ULTIMO STATUS')),
            })

    return registros


COLUNAS = [
    'conta_id',
    'documento',
    'stonecode',
    'data_venda',
    'bandeira',
    'produto',
    'stone_id',
    'n_parcelas',
    'valor_bruto',
    'valor_liquido',
    'desconto_mdr',
    'desconto_antecipacao',
    'desconto_unificado',
    'n_cartao',
    'meio_captura',
    'n_serie',
    'ultimo_status',
    'data_ultimo_status',
]


def resumo(registros):
    from collections import Counter

    print(f"  linhas lidas:        {len(registros)}")

    ids = set(r['stone_id'] for r in registros)
    print(f"  STONE ID unicos:     {len(ids)} (duplicatas no proprio arquivo: {len(registros) - len(ids)})")

    print(f"  status:              {dict(Counter(r['ultimo_status'] for r in registros))}")
    print(f"  soma valor bruto:    {sum(r['valor_bruto'] or 0 for r in registros):,.2f}")
    print(f"  soma valor liquido:  {sum(r['valor_liquido'] or 0 for r in registros):,.2f}")


# ---- gravacao no banco e recalculo do saldo -------------------------
def gravar(registros):
    if not registros:
        print("AVISO: nenhum registro para gravar.")
        return

    import os
    import psycopg2
    from psycopg2.extras import execute_values

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    url = os.environ.get('DATABASE_URL')

    if not url:
        print("ERRO: variavel DATABASE_URL nao encontrada (arquivo .env).")
        sys.exit(1)

    conn = None
    cur = None

    try:
        conn = psycopg2.connect(url)
        conn.autocommit = False
        cur = conn.cursor()

        cur.execute("select id from conta where nome = 'Stone' limit 1;")
        r = cur.fetchone()

        if not r:
            print("ERRO: conta 'Stone' nao encontrada. Rode o arquivo 01 (schema) antes.")
            conn.rollback()
            sys.exit(1)

        conta_id = r[0]

        valores = [
            [conta_id] + [reg[c] for c in COLUNAS[1:]]
            for reg in registros
        ]

        sql = f"""
            insert into raw_stone_vendas ({', '.join(COLUNAS)})
            values %s
            on conflict (stone_id) do nothing
            returning 1
        """

        inseridos_retorno = execute_values(
            cur,
            sql,
            valores,
            page_size=500,
            fetch=True
        )

        inseridos = len(inseridos_retorno)

        # Primeiro salva a importacao.
        conn.commit()

        print(f"  novas linhas inseridas: {inseridos}")
        print(f"  ja existiam (ignoradas): {len(registros) - inseridos}")

        # Recalculo defensivo: usa a data da venda como periodo impactado.
        datas_validas = [
            reg['data_venda'].date()
            for reg in registros
            if reg.get('data_venda') is not None
        ]

        if datas_validas:
            data_min_importada = min(datas_validas)
            data_max_importada = max(datas_validas)

            print("\n== Recalculando saldo de fechamento ==")
            print(f"  periodo impactado: {data_min_importada} ate {data_max_importada}")

            cur.execute(
                "select * from recalcular_saldo_fechamento(%s, %s, 0);",
                (data_min_importada, data_max_importada)
            )

            resultado = cur.fetchall()

            cur.execute(
                "insert into log_carga (fontes) values (%s);",
                ("Vendas Stone",)
            )

            conn.commit()

            print("  saldo recalculado com sucesso.")
            print("  log de carga registrado.")


            if resultado:
                print(f"  retorno: {resultado}")

        else:
            print("\nAVISO: nenhuma data valida encontrada. Saldo de fechamento nao recalculado.")

    except Exception as e:
        if conn:
            conn.rollback()

        print("\nERRO ao gravar/recalcular saldo:")
        print(e)
        sys.exit(1)

    finally:
        if cur:
            cur.close()

        if conn:
            conn.close()


# ---- main -----------------------------------------------------------
def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    dry = '--dry-run' in sys.argv

    if not args:
        print("Uso: python 09_importar_vendas_stone.py <arquivo.csv> [--dry-run]")
        sys.exit(1)

    caminho = args[0]

    print(f"Lendo: {caminho}")

    registros = ler_csv(caminho)

    print("\n== Resumo do arquivo ==")
    resumo(registros)

    if dry:
        print("\n[DRY-RUN] Nada foi gravado no banco.")
    else:
        print("\n== Gravando no banco ==")
        gravar(registros)

    print("\nOK.")


if __name__ == '__main__':
    main()
