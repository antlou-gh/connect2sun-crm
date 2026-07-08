"""API de máquina (/api/v1) — para o futuro servidor MCP.

Autenticada SÓ por chave estática (X-API-Key), nunca por sessão de browser
(ver require_login em blueprints/auth.py). Menor privilégio possível:

- POST /api/v1/transacoes  — criar movimento (única operação de escrita).
- GET  /api/v1/clientes    — listar/filtrar clientes (read-only).
- GET  /api/v1/transacoes  — consultar movimentos (read-only).

NÃO existem PUT/DELETE: a máquina nunca altera nem apaga. Se a chave vazar, o
estrago possível fica limitado a "criar movimentos a mais" e "ler dados".
"""

from flask import Blueprint, jsonify, request
from sqlalchemy import extract

from .. import db
from ..models import Transacao, Client
from ..financeiro_service import criar_transacao_from_dict

bp = Blueprint("api_v1", __name__)


@bp.post("/transacoes")
def criar_transacao():
    """Cria um movimento. Mesma validação que o endpoint humano (função
    partilhada criar_transacao_from_dict). Erros → 400; sucesso → 201."""
    body = request.get_json(silent=True) or {}
    t, erros = criar_transacao_from_dict(body)
    if erros:
        return jsonify({"error": "; ".join(erros)}), 400
    db.session.add(t)
    db.session.commit()
    return jsonify(t.to_dict()), 201


@bp.get("/clientes")
def listar_clientes():
    """Lista clientes. Com ?nif=... filtra por NIF exato (0, 1 ou vários);
    serve para o Cowork resolver NIF → cliente_id."""
    query = Client.query
    nif = (request.args.get("nif") or "").strip()
    if nif:
        query = query.filter(Client.nif == nif)
    clientes = query.order_by(Client.client_number.asc().nullslast()).all()
    return jsonify([c.to_dict() for c in clientes])


@bp.get("/transacoes")
def listar_transacoes():
    """Consulta movimentos (read-only). Espelha os filtros do list_transacoes
    humano: ano, mes, tipo_movimento, categoria, estado, entidade_emissora,
    cliente_id, q."""
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
