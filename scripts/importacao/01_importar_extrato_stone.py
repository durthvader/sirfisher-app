#!/usr/bin/env python3
# =====================================================================
# SIR FISHER - ETAPA 1 - Arquivo 03
# Importador do EXTRATO STONE (Comprovante de Extrato.csv)
#
# O que faz:
#   1. le o CSV cru do extrato Stone
#   2. limpa (valor/saldo no formato brasileiro, datas)
#   3. calcula um hash unico por linha (dedup)
#   4. insere em raw_stone_extrato; o que ja existe e ignorado
#   5. recalcula automaticamente o saldo de fechamento mensal
#
# COMO RODAR:
#   Simulacao (nao toca no banco, so confere o arquivo):
#       python 03_importar_extrato_stone.py ComprovanteDeExtrato.csv --dry-run
#
#   De verdade (precisa do .env com DATABASE_URL):
#       python 03_importar_extrato_stone.py ComprovanteDeExtrato.csv
#
# Reimportar o mesmo mes e SEGURO: so entra o que ainda nao existe.
# =====================================================================

import sys
import csv
import re
import hashlib
from datetime import datetime


# ---- parsing de valores no formato brasileiro -----------------------
def parse_valor(s):
    """ '-199,00' -> -199.0 ; 'R$ 69.514,95' -> 69514.95 ; 'Gratis' -> None """
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
    """ '26/06/2026 10:35' -> datetime ; tolera so data """
    s = (s or '').strip()

    for fmt in ('%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M', '%d/%m/%Y'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue

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
        reader = csv.DictReader(fh, delimiter=',')

        for row in reader:
            valor_raw = g(row, 'Valor')
            saldo_dep = g(row, 'Saldo depois')
            data_raw = g(row, 'Data')
            horario = g(row, 'Horário')
            dest_doc = g(row, 'Destino Documento')

            # hash de deduplicacao: usa os textos crus para ficar estavel
            base = f"{data_raw}|{horario}|{valor_raw}|{saldo_dep}|{dest_doc}"
            dedup_hash = hashlib.md5(base.encode('utf-8')).hexdigest()

            registros.append({
                'movimentacao':        g(row, 'Movimentação'),
                'tipo':                g(row, 'Tipo'),
                'valor':               parse_valor(valor_raw),
                'saldo_antes':         parse_valor(g(row, 'Saldo antes')),
                'saldo_depois':        parse_valor(saldo_dep),
                'tarifa':              g(row, 'Tarifa'),
                'data_hora':           parse_data(data_raw),
                'data_hora_raw':       data_raw,
                'horario':             horario,
                'situacao':            g(row, 'Situação'),
                'nosso_numero':        g(row, 'Nosso Número'),
                'destino':             g(row, 'Destino'),
                'destino_documento':   dest_doc,
                'destino_instituicao': g(row, 'Destino Instituição'),
                'destino_agencia':     g(row, 'Destino Agência'),
                'destino_conta':       g(row, 'Destino Conta'),
                'origem':              g(row, 'Origem'),
                'origem_documento':    g(row, 'Origem Documento'),
                'origem_instituicao':  g(row, 'Origem Instituição'),
                'origem_agencia':      g(row, 'Origem Agência'),
                'origem_conta':        g(row, 'Origem Conta'),
                'descricao':           g(row, 'Descrição'),
                'dedup_hash':          dedup_hash,
            })

    return registros


COLUNAS = [
    'conta_id',
    'movimentacao',
    'tipo',
    'valor',
    'saldo_antes',
    'saldo_depois',
    'tarifa',
    'data_hora',
    'data_hora_raw',
    'horario',
    'situacao',
    'nosso_numero',
    'destino',
    'destino_documento',
    'destino_instituicao',
    'destino_agencia',
    'destino_conta',
    'origem',
    'origem_documento',
    'origem_instituicao',
    'origem_agencia',
    'origem_conta',
    'descricao',
    'origem_carga',
    'dedup_hash',
]


def resumo(registros):
    from collections import Counter

    print(f"  linhas lidas:        {len(registros)}")

    mov = Counter(r['movimentacao'] for r in registros)
    print(f"  movimentacao:        {dict(mov)}")

    hashes = set(r['dedup_hash'] for r in registros)
    print(f"  hashes unicos:       {len(hashes)} (duplicatas no proprio arquivo: {len(registros) - len(hashes)})")

    sem_data = sum(1 for r in registros if r['data_hora'] is None)
    sem_valor = sum(1 for r in registros if r['valor'] is None)

    print(f"  sem data valida:     {sem_data}")
    print(f"  sem valor valido:    {sem_valor}")

    if registros:
        cred = sum(r['valor'] or 0 for r in registros if r['movimentacao'] == 'Crédito')
        deb = sum(r['valor'] or 0 for r in registros if r['movimentacao'] == 'Débito')

        print(f"  soma creditos:       {cred:,.2f}")
        print(f"  soma debitos:        {deb:,.2f}")


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
        print("ERRO: variavel DATABASE_URL nao encontrada. Crie um arquivo .env com:")
        print('  DATABASE_URL="postgresql://...sua conexao do Supabase..."')
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
            [conta_id]
            + [reg[c] for c in COLUNAS[1:-2]]
            + ['stone_extrato', reg['dedup_hash']]
            for reg in registros
        ]

        sql = f"""
            insert into raw_stone_extrato ({', '.join(COLUNAS)})
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
            reg['data_hora'].date()
            for reg in registros
            if reg.get('data_hora') is not None
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
                ("Extrato Stone",)
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


# ---- atualizacao do painel -----------------------------------------
def atualizar_painel():
    """Atualiza o snapshot do painel (mv_fluxo_caixa_diario) via refresh_painel().

    Best-effort: roda numa conexao propria, depois da carga ja comitada.
    Se a funcao ainda nao existir (migration nao aplicada) ou falhar,
    apenas avisa -- a importacao ja esta salva e nao e desfeita.
    """
    import os
    import psycopg2

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    url = os.environ.get('DATABASE_URL')

    if not url:
        print("  AVISO: DATABASE_URL nao encontrada; painel nao atualizado.")
        return

    try:
        conn = psycopg2.connect(url)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("select refresh_painel();")
        cur.close()
        conn.close()
        print("  painel atualizado (mv_fluxo_caixa_diario).")
    except Exception as e:
        print(f"  AVISO: nao foi possivel atualizar o painel: {e}")


# ---- main -----------------------------------------------------------
def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    dry = '--dry-run' in sys.argv

    if not args:
        print("Uso: python 03_importar_extrato_stone.py <arquivo.csv> [--dry-run]")
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

        print("\n== Atualizando painel ==")
        atualizar_painel()

    print("\nOK.")


if __name__ == '__main__':
    main()