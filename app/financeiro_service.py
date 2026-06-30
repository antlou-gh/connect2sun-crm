"""Serviços partilhados do módulo financeiro: importação e exportação Excel.

Princípios:
- **Ler/escrever SEMPRE por nome de cabeçalho**, nunca por posição de coluna
  (no ficheiro real o "NIF" está na coluna D, a seguir à "Descrição", o que
  desloca as colunas seguintes — o mapeamento posicional falharia).
- O export é um **snapshot unidirecional** (app → Excel). A app é a fonte de
  verdade; ficheiros exportados nunca são reimportados.
"""

import os
import unicodedata
from datetime import date

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter, range_boundaries

from . import db
from .models import Transacao, Client, MESES

SHEET_NAME = "BD Financeira 2026"
TABELA = "Tabela2"

# Caminho do ficheiro-modelo (cabeçalhos + estilos, sem dados) usado pelo export.
MODELO_PATH = os.path.join(
    os.path.dirname(__file__), "static", "templates_xlsx",
    "BD_Financeira_2026_modelo.xlsx",
)

# Cabeçalhos esperados na Tabela2 (textos exatos confirmados no ficheiro real).
CAB_NUMERO = "Nº de ordem"
CAB_DESCRICAO = "Descrição"
CAB_NIF = "NIF"
CAB_VALOR = "Valor total"
CAB_ENTIDADE = "Entidade emissora"
CAB_FACTURA = "Nº de factura"
CAB_SIVA = "S/ IVA"
CAB_IVA = "IVA"
CAB_IVA_PCT = "IVA %"
CAB_DIA = "Dia"
CAB_MES = "Mês"
CAB_TOTAL = "Total"
CAB_ESTADO = "Estado"
CAB_TIPO = "Tipo de movimento"

# Cabeçalhos obrigatórios para o import funcionar.
CABECALHOS_IMPORT = [
    CAB_NUMERO, CAB_DESCRICAO, CAB_NIF, CAB_VALOR, CAB_ENTIDADE, CAB_FACTURA,
    CAB_SIVA, CAB_IVA_PCT, CAB_DIA, CAB_MES, CAB_ESTADO, CAB_TIPO,
]


# ── Normalização ──────────────────────────────────────────────────────────────

def _normalizar(texto):
    """trim + minúsculas + sem acentos — para comparar cabeçalhos de forma robusta."""
    if texto is None:
        return ""
    s = str(texto).strip().lower()
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def normalizar_nif(valor):
    """NIF → string canónica. No Excel vem como inteiro; no modelo é String(20).

    Converte com str(int(...)) quando numérico, tira espaços e um prefixo "PT".
    Devolve None se vazio.
    """
    if valor is None:
        return None
    if isinstance(valor, float):
        valor = int(valor)
    if isinstance(valor, int):
        s = str(valor)
    else:
        s = str(valor).strip().replace(" ", "")
        if s[:2].upper() == "PT":
            s = s[2:]
    s = s.strip()
    return s or None


def mes_para_numero(nome):
    """Nome do mês em português → 1..12. Tolera abreviaturas (ex.: 'Mar')."""
    if nome is None:
        return None
    alvo = _normalizar(nome)
    if not alvo:
        return None
    for i, m in enumerate(MESES, start=1):
        if _normalizar(m) == alvo:
            return i
    # Tolerância a abreviaturas: prefixo de 3 letras é único entre os 12 meses.
    if len(alvo) >= 3:
        for i, m in enumerate(MESES, start=1):
            if _normalizar(m).startswith(alvo[:3]):
                return i
    return None


# ── Localização da tabela / mapa de cabeçalhos ────────────────────────────────

def _selecionar_folha(wb):
    if SHEET_NAME in wb.sheetnames:
        return wb[SHEET_NAME]
    # Fallback: a folha que contém a Tabela2, senão a primeira.
    for ws in wb.worksheets:
        if TABELA in ws.tables:
            return ws
    return wb.worksheets[0]


def _limites_tabela(ws):
    """(min_col, header_row, max_col, max_row) da Tabela2; fallback B2:O? se ausente."""
    if TABELA in ws.tables:
        min_col, min_row, max_col, max_row = range_boundaries(ws.tables[TABELA].ref)
        return min_col, min_row, max_col, max_row
    # Sem tabela: assume cabeçalhos na linha 2, colunas B..O.
    return 2, 2, 15, ws.max_row


def _mapa_cabecalhos(ws, header_row, min_col, max_col):
    """{cabeçalho_normalizado: índice_coluna} lendo a linha de cabeçalhos."""
    mapa = {}
    for col in range(min_col, max_col + 1):
        valor = ws.cell(row=header_row, column=col).value
        chave = _normalizar(valor)
        if chave:
            mapa[chave] = col
    return mapa


def _exigir_cabecalhos(mapa, cabecalhos):
    em_falta = [c for c in cabecalhos if _normalizar(c) not in mapa]
    if em_falta:
        raise ValueError(
            "Cabeçalhos em falta na folha (lidos por nome, não por posição): "
            + ", ".join(em_falta)
        )


# ── Importação ────────────────────────────────────────────────────────────────

def importar_financeiro(caminho_xlsx, ano=2026):
    """Importa os movimentos do .xlsx para a tabela `transacoes`.

    - Lê colunas por NOME de cabeçalho.
    - `categoria` fica sempre NULL (categorização é feita depois na app).
    - `cliente_id` resolvido por NIF (NULL se vazio/sem correspondência).
    - Idempotente: `numero_ordem` já existente é saltado (não duplica).

    Devolve um dicionário-resumo.
    """
    wb = load_workbook(caminho_xlsx, data_only=True)
    ws = _selecionar_folha(wb)
    min_col, header_row, max_col, max_row = _limites_tabela(ws)
    mapa = _mapa_cabecalhos(ws, header_row, min_col, max_col)
    _exigir_cabecalhos(mapa, CABECALHOS_IMPORT)

    def ler(row, cabecalho):
        col = mapa[_normalizar(cabecalho)]
        return ws.cell(row=row, column=col).value

    # Índice de clientes por NIF normalizado (resolução rápida).
    clientes_por_nif = {}
    for c in Client.query.filter(Client.nif.isnot(None), Client.nif != "").all():
        nif = normalizar_nif(c.nif)
        if nif:
            clientes_por_nif.setdefault(nif, c.id)

    # Nºs de ordem já existentes — para idempotência.
    existentes = {
        n for (n,) in db.session.query(Transacao.numero_ordem)
        .filter(Transacao.numero_ordem.isnot(None)).all()
    }

    importados = ja_existentes = sem_cliente = ignoradas = 0
    avisos = []

    for row in range(header_row + 1, max_row + 1):
        descricao = ler(row, CAB_DESCRICAO)
        if descricao is None or str(descricao).strip() == "":
            continue  # linha vazia / fantasma (a tabela tem nºs de ordem pré-preenchidos)

        numero = ler(row, CAB_NUMERO)
        try:
            numero = int(numero)
        except (TypeError, ValueError):
            avisos.append(f"Linha {row}: Nº de ordem inválido ({numero!r}); ignorada.")
            ignoradas += 1
            continue

        if numero in existentes:
            ja_existentes += 1
            continue

        valor = ler(row, CAB_VALOR)
        try:
            valor = float(valor)
        except (TypeError, ValueError):
            avisos.append(f"Linha {row} (ordem {numero}): Valor total inválido; ignorada.")
            ignoradas += 1
            continue

        # Data a partir de Dia + Mês (texto pt) + ano.
        dia = ler(row, CAB_DIA)
        mes_num = mes_para_numero(ler(row, CAB_MES))
        try:
            data = date(ano, mes_num, int(dia))
        except (TypeError, ValueError):
            avisos.append(
                f"Linha {row} (ordem {numero}): Dia/Mês inválido "
                f"({dia!r}/{ler(row, CAB_MES)!r}); ignorada."
            )
            ignoradas += 1
            continue

        valor_siva = ler(row, CAB_SIVA)
        try:
            valor_siva = float(valor_siva)
        except (TypeError, ValueError):
            valor_siva = None
        # IVA: na folha é fórmula =ABS([Valor total])-[S/ IVA]; não guardar a string.
        iva = round(abs(valor) - valor_siva, 2) if valor_siva is not None else None

        iva_pct = ler(row, CAB_IVA_PCT)
        try:
            iva_pct = float(iva_pct)
        except (TypeError, ValueError):
            iva_pct = None

        cliente_id = clientes_por_nif.get(normalizar_nif(ler(row, CAB_NIF)))
        if cliente_id is None:
            sem_cliente += 1

        def texto(cabecalho):
            v = ler(row, cabecalho)
            return str(v).strip() if v is not None and str(v).strip() != "" else None

        t = Transacao(
            numero_ordem=numero,
            descricao=str(descricao).strip(),
            valor=valor,
            entidade_emissora=texto(CAB_ENTIDADE),
            num_factura=texto(CAB_FACTURA),
            valor_siva=valor_siva,
            iva=iva,
            iva_pct=iva_pct,
            data=data,
            estado=texto(CAB_ESTADO),
            tipo_movimento=texto(CAB_TIPO),
            categoria=None,  # sempre NULL na importação
            cliente_id=cliente_id,
        )
        db.session.add(t)
        existentes.add(numero)
        importados += 1

    db.session.commit()

    return {
        "importados": importados,
        "ja_existentes": ja_existentes,
        "sem_cliente": sem_cliente,
        "sem_categoria": importados,  # categoria é sempre NULL na importação
        "ignoradas": ignoradas,
        "avisos": avisos,
    }


# ── Exportação (snapshot app → Excel) ─────────────────────────────────────────

def gerar_export_financeiro(ano=2026):
    """Gera um Workbook (snapshot) das transações do `ano` no formato da folha.

    Parte do ficheiro-modelo (preserva Tabela2, cabeçalhos, estilos e larguras).
    Read-only sobre a BD. Escreve cada campo na coluna do respetivo cabeçalho.
    """
    if not os.path.exists(MODELO_PATH):
        raise FileNotFoundError(
            f"Ficheiro-modelo do export não encontrado: {MODELO_PATH}"
        )

    wb = load_workbook(MODELO_PATH)  # ler fresco a cada chamada (não mutar partilhado)
    ws = _selecionar_folha(wb)
    min_col, header_row, max_col, max_row = _limites_tabela(ws)
    mapa = _mapa_cabecalhos(ws, header_row, min_col, max_col)
    # Para o export precisamos também do cabeçalho "Total".
    _exigir_cabecalhos(mapa, CABECALHOS_IMPORT + [CAB_TOTAL])

    transacoes = (
        Transacao.query
        .filter(db.extract("year", Transacao.data) == ano)
        .order_by(Transacao.numero_ordem.asc())
        .all()
    )

    def escrever(linha, cabecalho, valor):
        col = mapa[_normalizar(cabecalho)]
        ws.cell(row=linha, column=col, value=valor)

    linha = header_row
    for t in transacoes:
        linha += 1
        nif = normalizar_nif(t.cliente.nif) if t.cliente else None
        mes_nome = MESES[t.data.month - 1] if t.data else None
        escrever(linha, CAB_NUMERO, t.numero_ordem)
        escrever(linha, CAB_DESCRICAO, t.descricao)
        escrever(linha, CAB_NIF, nif or "")
        escrever(linha, CAB_VALOR, t.valor)
        escrever(linha, CAB_ENTIDADE, t.entidade_emissora)
        escrever(linha, CAB_FACTURA, t.num_factura)
        escrever(linha, CAB_SIVA, t.valor_siva)
        escrever(linha, CAB_IVA, t.iva)              # valor literal
        escrever(linha, CAB_IVA_PCT, t.iva_pct)
        escrever(linha, CAB_DIA, t.data.day if t.data else None)
        escrever(linha, CAB_MES, mes_nome)           # texto português
        escrever(linha, CAB_TOTAL, abs(t.valor) if t.valor is not None else None)  # literal, nunca fórmula
        escrever(linha, CAB_ESTADO, t.estado)
        escrever(linha, CAB_TIPO, t.tipo_movimento)
        # categoria NÃO é exportada (dimensão só da app; não existe na Tabela2).

    # Ajustar o intervalo da Tabela2 ao nº de linhas escritas.
    # Mínimo: cabeçalho + 1 linha (mantém a tabela válida mesmo sem dados).
    ultima = max(linha, header_row + 1)
    if TABELA in ws.tables:
        ref = (f"{get_column_letter(min_col)}{header_row}:"
               f"{get_column_letter(max_col)}{ultima}")
        ws.tables[TABELA].ref = ref

    return wb
