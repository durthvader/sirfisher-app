#!/usr/bin/env python3
# =====================================================================
# SIR FISHER - ETAPA 1 - Arquivo 11
# Importador do extrato BANCO DO BRASIL (conta corrente)
#
# O que faz:
#   1. le o CSV cru do extrato BB
#   2. filtra linhas de saldo que nao sao transacao
#   3. limpa datas e valores
#   4. calcula hash unico por linha (dedup)
#   5. insere em raw_bb; o que ja existe e ignorado
#   6. recalcula automaticamente o saldo de fechamento mensal
#
# COMO RODAR:
#   Simulacao (nao toca no banco):
#       python 11_importar_bb.py extrato_bb.csv --dry-run
#
#   De verdade (precisa do .env com DATABASE_URL):
#       python 11_importar_bb.py extrato_bb.csv
#
# Reimportar o mesmo periodo e SEGURO: so entra o que ainda nao existe.
# =====================================================================

import sys
import csv
import re
import hashlib
from datetime import datetime


LINHAS_NAO_TRANSACAO = {'Saldo Anterior', 'Saldo do dia', 'S A L D O'}


# ---- parsing de valores no formato brasileiro -----------------------
def parse_valor(s):
    """ '-13.589,34 D' -> -13589.34 ; '10.000,00 C' -> 10000.0 """
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

    try:
        return datetime.strptime(s, '%d/%m/%Y').date()
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
    ignoradas_saldo = 0

    with open(caminho, encoding='latin-1', newline='') as fh:
        reader = csv.DictReader(fh, delimiter=',')

        for row in reader:
            lancamento = g(row, 'Lançamento')

            if lancamento in LINHAS_NAO_TRANSACAO:
                ignoradas_saldo += 1
                continue

            data_raw = g(row, 'Data')
            n_doc = g(row, 'N° documento')
            valor_raw = g(row, 'Valor')
            detalhes = g(row, 'Detalhes')
            tipo = g(row, 'Tipo Lançamento')

            # hash de deduplicacao: usa os textos crus para ficar estavel
            base = f"{data_raw}|{lancamento}|{n_doc}|{valor_raw}|{detalhes}"
            dedup_hash = hashlib.md5(base.encode('utf-8')).hexdigest()

            registros.append({
                'data':             parse_data(data_raw),
                'data_raw':         data_raw,
                'lancamento':       lancamento,
                'detalhes':         detalhes,
                'n_documento':      n_doc,
                'valor':            parse_valor(valor_raw),
                'tipo_lancamento':  tipo,
                'dedup_hash':       dedup_hash,
            })

    return registros, ignoradas_saldo


COLUNAS = [
    'conta_id',
    'data',
    'data_raw',
    'lancamento',
    'detalhes',
    'n_documento',
    'valor',
    'tipo_lancamento',
    'dedup_hash',
]


def resumo(registros, ignoradas_saldo):
    from collections import Counter

    print(f"  linhas de transacao:   {len(registros)}")
    print(f"  linhas de saldo (fora): {ignoradas_saldo}")

    hashes = set(r['dedup_hash'] for r in registros)
    print(f"  hashes unicos:          {len(hashes)} (duplicatas no arquivo: {len(registros) - len(hashes)})")

    sem_data = sum(1 for r in registros if r['data'] is None)
    sem_valor = sum(1 for r in registros if r['valor'] is None)

    print(f"  sem data valida:        {sem_data}")
    print(f"  sem valor valido:       {sem_valor}")
    print(f"  tipo lancamento:        {dict(Counter(r['tipo_lancamento'] for r in registros))}")

    ent = sum(r['valor'] or 0 for r in registros if (r['valor'] or 0) > 0)
    sai = sum(r['valor'] or 0 for r in registros if (r['valor'] or 0) < 0)

    print(f"  soma entradas:          {ent:,.2f}")
    print(f"  soma saidas:            {sai:,.2f}")


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

        cur.execute("select id from conta where nome = 'Banco do Brasil' limit 1;")
        r = cur.fetchone()

        if not r:
            print("ERRO: conta 'Banco do Brasil' nao encontrada. Rode o arquivo 01 (schema) antes.")
            conn.rollback()
            sys.exit(1)

        conta_id = r[0]

        valores = [
            [conta_id] + [reg[c] for c in COLUNAS[1:]]
            for reg in registros
        ]

        sql = f"""
            insert into raw_bb ({', '.join(COLUNAS)})
            values %s
            on conflict (dedup_hash) do nothing
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

        # Recalcula o saldo fechado com base no intervalo do arquivo lido.
        # Mesmo se tudo ja existia, recalcular e seguro.
        datas_validas = [
            reg['data']
            for reg in registros
            if reg.get('data') is not None
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
                ("Extrato BB",)
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
        print("Uso: python 11_importar_bb.py <arquivo.csv> [--dry-run]")
        sys.exit(1)

    caminho = args[0]

    print(f"Lendo: {caminho}")

    registros, ignoradas = ler_csv(caminho)

    print("\n== Resumo do arquivo ==")
    resumo(registros, ignoradas)

    if dry:
        print("\n[DRY-RUN] Nada foi gravado no banco.")
    else:
        print("\n== Gravando no banco ==")
        gravar(registros)

    print("\nOK.")


if __name__ == '__main__':
    main()
