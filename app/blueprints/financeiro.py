"""Módulo financeiro — CRUD de movimentos, ecrãs de revisão, dashboards e export.

A app é a fonte de verdade dos movimentos (substitui o Excel). Todas as rotas
herdam a autenticação global (before_request em app/__init__).
"""

import io
from datetime import date

from flask import Blueprint, jsonify, request, send_file
from sqlalchemy import extract

from .. import db
from ..models import (
    Transacao, Client,
    ESTADOS, TIPOS_MOVIMENTO, CATEGORIAS, MESES,
)
# Regra de negócio de criação/aplicação de campos vive no serviço partilhado
# (fonte única, reutilizada também pela API de máquina /api/v1).
from ..financeiro_service import criar_transacao_from_dict, _aplicar_campos

bp = Blueprint("financeiro", __name__)

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Tipos que requerem categoria (ecrã "por categorizar").
TIPOS_COM_CATEGORIA = ("Custos gerais", "Pagamentos ao Estado")
# Tipos que deviam ter cliente (ecrã "por associar a cliente").
TIPOS_COM_CLIENTE = ("Facturação", "Material/Serviços")


def _siva(t):
    """Valor SEM IVA, com o sinal do movimento — base de todos os P&L.

    O IVA não é receita nem custo da empresa (é entregue ao/recuperado do
    Estado), por isso receita e custos calculam-se sempre sobre a base
    sem IVA.

    Convenções dos dados:
    - `valor_siva` é uma magnitude (na folha, "S/ IVA" é sempre positivo:
      o IVA é calculado como ABS(Valor total) − S/IVA). O sinal do movimento
      vive SEMPRE em `valor`. Usa-se abs() por robustez, caso algum registo
      tenha entrado já com sinal via API.
    - Movimentos sem `valor_siva` (ex.: Pagamentos ao Estado, vencimentos —
      sem IVA) usam o próprio `valor` como fallback.
    """
    if t.valor_siva is None:
        return t.valor or 0.0
    mag = abs(t.valor_siva)
    return mag if (t.valor or 0.0) >= 0 else -mag


# ── Metadados (constantes + clientes) para dropdowns ──────────────────────────

@bp.get("/meta")
def meta():
    clientes = (
        Client.query.order_by(Client.client_number.asc().nullslast())
        .with_entities(Client.id, Client.client_number, Client.name)
        .all()
    )
    entidades_emissoras = [
        e for (e,) in (
            db.session.query(Transacao.entidade_emissora)
            .filter(Transacao.entidade_emissora.isnot(None))
            .distinct()
            .order_by(Transacao.entidade_emissora.asc())
            .all()
        )
    ]
    return jsonify({
        "estados": ESTADOS,
        "tipos_movimento": TIPOS_MOVIMENTO,
        "categorias": CATEGORIAS,
        "meses": MESES,
        "entidades_emissoras": entidades_emissoras,
        "clientes": [
            {"id": c.id, "client_number": c.client_number, "name": c.name}
            for c in clientes
        ],
    })


# ── CRUD de movimentos ────────────────────────────────────────────────────────

@bp.get("/transacoes")
def list_transacoes():
    query = Transacao.query
    ano = request.args.get("ano", type=int)
    mes = request.args.get("mes", type=int)
    tipo = request.args.get("tipo_movimento")
    categoria = request.args.get("categoria")
    estado = request.args.get("estado")
    entidade_emissora = request.args.get("entidade_emissora")
    cliente_id = request.args.get("cliente_id", type=int)
    q = (request.args.get("q") or "").strip()

    if ano:
        query = query.filter(extract("year", Transacao.data) == ano)
    if mes:
        query = query.filter(extract("month", Transacao.data) == mes)
    if tipo:
        query = query.filter(Transacao.tipo_movimento == tipo)
    if categoria == "__none__":
        query = query.filter(Transacao.categoria.is_(None))
    elif categoria:
        query = query.filter(Transacao.categoria == categoria)
    if estado:
        query = query.filter(Transacao.estado == estado)
    if entidade_emissora == "__none__":
        query = query.filter(Transacao.entidade_emissora.is_(None))
    elif entidade_emissora:
        query = query.filter(Transacao.entidade_emissora == entidade_emissora)
    if cliente_id:
        query = query.filter(Transacao.cliente_id == cliente_id)
    if q:
        query = query.filter(Transacao.descricao.ilike(f"%{q}%"))

    transacoes = query.order_by(
        Transacao.data.desc(), Transacao.numero_ordem.desc()
    ).all()
    return jsonify([t.to_dict() for t in transacoes])


@bp.post("/transacoes")
def create_transacao():
    body = request.get_json(silent=True) or {}
    t, erros = criar_transacao_from_dict(body)
    if erros:
        return jsonify({"error": "; ".join(erros)}), 400
    db.session.add(t)
    db.session.commit()
    return jsonify(t.to_dict()), 201


@bp.put("/transacoes/<int:transacao_id>")
def update_transacao(transacao_id):
    t = db.get_or_404(Transacao, transacao_id)
    body = request.get_json(silent=True) or {}
    erros = _aplicar_campos(t, body)
    if erros:
        return jsonify({"error": "; ".join(erros)}), 400
    db.session.commit()
    return jsonify(t.to_dict())


@bp.delete("/transacoes/<int:transacao_id>")
def delete_transacao(transacao_id):
    t = db.get_or_404(Transacao, transacao_id)
    db.session.delete(t)
    db.session.commit()
    return "", 204


# ── Ecrãs de revisão (derivados por query) ────────────────────────────────────

@bp.get("/por-categorizar")
def por_categorizar():
    """categoria IS NULL e tipo em (Custos gerais, Pagamentos ao Estado)."""
    transacoes = (
        Transacao.query
        .filter(Transacao.categoria.is_(None))
        .filter(Transacao.tipo_movimento.in_(TIPOS_COM_CATEGORIA))
        .order_by(Transacao.data.desc(), Transacao.numero_ordem.desc())
        .all()
    )
    return jsonify([t.to_dict() for t in transacoes])


@bp.get("/por-associar")
def por_associar():
    """cliente_id IS NULL e tipo em (Facturação, Material/Serviços)."""
    transacoes = (
        Transacao.query
        .filter(Transacao.cliente_id.is_(None))
        .filter(Transacao.tipo_movimento.in_(TIPOS_COM_CLIENTE))
        .order_by(Transacao.data.desc(), Transacao.numero_ordem.desc())
        .all()
    )
    return jsonify([t.to_dict() for t in transacoes])


# ── Dashboards ────────────────────────────────────────────────────────────────

def _calcular_pl(rows):
    """Totais de P&L (base sem IVA) para um conjunto de movimentos.

    Partilhado entre `dashboard_pl` e `dashboard_mensal` — fonte única da
    regra de negócio (ver _siva para a base sem IVA e a direção da NC:
    NC negativa (venda anulada) abate à faturação; NC positiva (de
    fornecedor) abate aos custos diretos).
    """
    faturacao = sum(_siva(t) for t in rows if t.tipo_movimento == "Facturação")
    faturacao += sum(_siva(t) for t in rows
                      if t.tipo_movimento == "Nota de crédito" and t.valor < 0)
    custos_diretos = sum(abs(_siva(t)) for t in rows
                         if t.tipo_movimento == "Material/Serviços")
    custos_diretos -= sum(_siva(t) for t in rows
                          if t.tipo_movimento == "Nota de crédito" and t.valor > 0)

    estrutura_rows = [t for t in rows
                      if t.tipo_movimento in ("Custos gerais", "Pagamentos ao Estado")]
    custos_estrutura = sum(abs(_siva(t)) for t in estrutura_rows)

    breakdown = {}
    for t in estrutura_rows:
        chave = t.categoria or "Sem categoria"
        breakdown[chave] = breakdown.get(chave, 0.0) + abs(_siva(t))

    custos = custos_diretos + custos_estrutura
    resultado = faturacao - custos

    return {
        "faturacao": faturacao,
        "custos_diretos": custos_diretos,
        "custos_estrutura": custos_estrutura,
        "custos": custos,
        "resultado": resultado,
        "num_movimentos": len(rows),
        "breakdown_estrutura": breakdown,
    }


@bp.get("/dashboard/pl")
def dashboard_pl():
    """P&L geral, com filtro opcional de mês/ano."""
    ano = request.args.get("ano", type=int) or date.today().year
    mes = request.args.get("mes", type=int)

    query = Transacao.query.filter(extract("year", Transacao.data) == ano)
    if mes:
        query = query.filter(extract("month", Transacao.data) == mes)
    rows = query.all()

    c = _calcular_pl(rows)
    return jsonify({
        "ano": ano,
        "mes": mes,
        "receita": round(c["faturacao"], 2),
        "custos_diretos": round(c["custos_diretos"], 2),
        "custos_estrutura": round(c["custos_estrutura"], 2),
        "breakdown_estrutura": {k: round(v, 2) for k, v in
                                sorted(c["breakdown_estrutura"].items(), key=lambda x: -x[1])},
        "resultado": round(c["resultado"], 2),
        "num_movimentos": c["num_movimentos"],
    })


@bp.get("/dashboard/mensal")
def dashboard_mensal():
    """Dashboard mensal (faturação/custos/resultado por mês), base sem IVA.

    Devolve sempre os 12 meses (com zeros quando não há movimentos), para o
    gráfico de barras agrupadas do frontend.
    """
    ano = request.args.get("ano", type=int) or date.today().year

    rows = Transacao.query.filter(extract("year", Transacao.data) == ano).all()
    por_mes = {m: [] for m in range(1, 13)}
    for t in rows:
        por_mes[t.data.month].append(t)

    meses = []
    for m in range(1, 13):
        c = _calcular_pl(por_mes[m])
        meses.append({
            "mes": m,
            "mes_nome": MESES[m - 1],
            "faturacao": round(c["faturacao"], 2),
            "custos_diretos": round(c["custos_diretos"], 2),
            "custos_estrutura": round(c["custos_estrutura"], 2),
            "custos": round(c["custos"], 2),
            "resultado": round(c["resultado"], 2),
            "num_movimentos": c["num_movimentos"],
        })

    # Totais do ano == _calcular_pl sobre todos os movimentos (soma é aditiva
    # por partição de meses; evita reacumular campo a campo).
    t = _calcular_pl(rows)
    return jsonify({
        "ano": ano,
        "meses": meses,
        "totais": {
            "faturacao": round(t["faturacao"], 2),
            "custos_diretos": round(t["custos_diretos"], 2),
            "custos_estrutura": round(t["custos_estrutura"], 2),
            "custos": round(t["custos"], 2),
            "resultado": round(t["resultado"], 2),
            "num_movimentos": t["num_movimentos"],
        },
    })


def _margem_cliente(cliente_id, ano=None):
    """(faturacao, custos, margem) de um cliente. ano=None → todos os anos."""
    query = Transacao.query.filter(Transacao.cliente_id == cliente_id)
    if ano:
        query = query.filter(extract("year", Transacao.data) == ano)
    rows = query.all()
    faturacao = 0.0
    custos = 0.0
    # Base SEM IVA (ver _siva); direção da NC decidida pelo sinal de `valor`.
    for t in rows:
        if t.tipo_movimento == "Facturação":
            faturacao += _siva(t)
        elif t.tipo_movimento == "Nota de crédito":
            if t.valor < 0:
                faturacao += _siva(t)  # NC de venda: abate à facturação
            else:
                custos -= _siva(t)     # NC de fornecedor: abate aos custos
        elif t.tipo_movimento == "Material/Serviços":
            custos += abs(_siva(t))
    return round(faturacao, 2), round(custos, 2), round(faturacao - custos, 2)


@bp.get("/dashboard/margem-cliente")
def dashboard_margem_cliente():
    """Margem por cliente (Σ Facturação − Σ Material/Serviços), ordenável."""
    ano = request.args.get("ano", type=int)

    query = Transacao.query.filter(Transacao.cliente_id.isnot(None))
    if ano:
        query = query.filter(extract("year", Transacao.data) == ano)
    rows = query.all()

    agg = {}  # cliente_id -> {faturacao, custos}
    for t in rows:
        a = agg.setdefault(t.cliente_id, {
            "faturacao": 0.0, "custos": 0.0,
            "cliente_nome": t.cliente.name if t.cliente else None,
            "cliente_numero": t.cliente.client_number if t.cliente else None,
        })
        # Base SEM IVA (ver _siva); direção da NC pelo sinal de `valor`.
        if t.tipo_movimento == "Facturação":
            a["faturacao"] += _siva(t)
        elif t.tipo_movimento == "Nota de crédito":
            if t.valor < 0:
                a["faturacao"] += _siva(t)  # NC de venda: abate à facturação
            else:
                a["custos"] -= _siva(t)     # NC de fornecedor: abate aos custos
        elif t.tipo_movimento == "Material/Serviços":
            a["custos"] += abs(_siva(t))

    resultado = []
    for cid, a in agg.items():
        resultado.append({
            "cliente_id": cid,
            "cliente_nome": a["cliente_nome"],
            "cliente_numero": a["cliente_numero"],
            "faturacao": round(a["faturacao"], 2),
            "custos": round(a["custos"], 2),
            "margem": round(a["faturacao"] - a["custos"], 2),
        })
    resultado.sort(key=lambda x: x["margem"], reverse=True)
    return jsonify(resultado)


@bp.get("/cliente/<int:cliente_id>")
def cliente_financeiro(cliente_id):
    """Bloco financeiro da ficha do cliente: margem + lista de movimentos."""
    db.get_or_404(Client, cliente_id)
    faturacao, custos, margem = _margem_cliente(cliente_id)
    movimentos = (
        Transacao.query.filter(Transacao.cliente_id == cliente_id)
        .order_by(Transacao.data.desc(), Transacao.numero_ordem.desc())
        .all()
    )
    return jsonify({
        "faturacao": faturacao,
        "custos": custos,
        "margem": margem,
        "movimentos": [t.to_dict() for t in movimentos],
    })


# ── Exportação para Excel (snapshot app → ficheiro novo) ──────────────────────

@bp.get("/exportar")
def exportar():
    from ..financeiro_service import gerar_export_financeiro
    ano = request.args.get("ano", type=int) or date.today().year
    wb = gerar_export_financeiro(ano=ano)
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    nome = f"BD Financeira_export_{date.today():%Y%m%d}.xlsx"
    return send_file(
        buffer, mimetype=XLSX_MIME, as_attachment=True, download_name=nome
    )
