"""API de máquina (/api/v1) — para o servidor MCP.

Autenticada SÓ por chave estática (X-API-Key), nunca por sessão de browser
(ver require_login em blueprints/auth.py). Duas chaves possíveis, cada uma
com uma role (ver app/api_auth.py):

- MCP_API_KEY          → role "admin"        — ler, criar, editar.
- MCP_API_KEY_READONLY → role "contabilista" — só ler.

Rotas:
- POST  /api/v1/transacoes      — criar movimento (role admin).
- PATCH /api/v1/transacoes/<id> — editar campos pontuais (role admin).
- GET   /api/v1/clientes        — listar/filtrar clientes (qualquer role).
- GET   /api/v1/transacoes      — consultar movimentos (qualquer role).
- GET   /api/v1/saldo           — totais agregados por NIF (qualquer role).

NÃO existe DELETE: não há caso de uso identificado para apagar movimentos via
máquina, e é a única operação que não se consegue desfazer com outro PATCH.
"""

from flask import Blueprint, g, jsonify, request
from sqlalchemy import extract

from .. import db
from ..financeiro_service import (
    atualizar_transacao_from_dict,
    criar_transacao_from_dict,
    saldo_por_nif,
)
from ..models import Client, Transacao

bp = Blueprint("api_v1", __name__)


def _exigir_admin():
    """403 se a chave usada for só-leitura (role "contabilista"). None se ok.

    role_da_chave() já correu no require_login (blueprints/auth.py) e deixou
    o resultado em g.mcp_role antes de qualquer rota da api_v1 ser chamada.
    """
    if g.get("mcp_role") != "admin":
        return jsonify({"error": "Só disponível para a chave de escrita (admin)."}), 403
    return None


@bp.post("/transacoes")
def criar_transacao():
    """Cria um movimento. Mesma validação que o endpoint humano (função
    partilhada criar_transacao_from_dict). Erros → 400; sucesso → 201."""
    erro = _exigir_admin()
    if erro:
        return erro
    body = request.get_json(silent=True) or {}
    t, erros = criar_transacao_from_dict(body)
    if erros:
        return jsonify({"error": "; ".join(erros)}), 400
    db.session.add(t)
    db.session.commit()
    return jsonify(t.to_dict()), 201


@bp.patch("/transacoes/<int:transacao_id>")
def atualizar_transacao(transacao_id):
    """Edita campos pontuais de um movimento existente (PATCH parcial).

    Só os campos presentes no corpo são alterados; ver
    financeiro_service.atualizar_transacao_from_dict para as regras
    (campos imutáveis, entidade_emissora, recálculo de IVA).
    """
    erro = _exigir_admin()
    if erro:
        return erro
    t = db.session.get(Transacao, transacao_id)
    if t is None:
        return jsonify({"error": "Movimento não encontrado."}), 404
    body = request.get_json(silent=True) or {}
    t, erros, avisos = atualizar_transacao_from_dict(t, body)
    if erros:
        db.session.rollback()  # não deixar nada de _aplicar_campos meio-aplicado
        return jsonify({"error": "; ".join(erros)}), 400
    db.session.commit()
    resposta = t.to_dict()
    if avisos:
        resposta["avisos"] = avisos
    return jsonify(resposta), 200


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

    transacoes = query.order_by(Transacao.data.desc(), Transacao.numero_ordem.desc()).all()
    return jsonify([t.to_dict() for t in transacoes])


@bp.get("/saldo")
def saldo():
    """Totais agregados dos movimentos de um cliente, por NIF (read-only).

    Existe para o servidor MCP não ter de puxar a lista toda para somar: essa
    listagem é truncada às 100 linhas, pelo que somar do lado do cliente daria
    um total errado sem dar sinal disso.

    `?nif=` obrigatório; `?ano=` opcional. NIF desconhecido devolve **200** com
    `encontrado: false`, não 404 nem saldo 0 — a diferença entre "não há esse
    cliente" e "esse cliente está a zero" tem de chegar intacta a quem chama.
    """
    nif = (request.args.get("nif") or "").strip()
    if not nif:
        return jsonify({"error": "Parâmetro nif é obrigatório."}), 400
    ano = request.args.get("ano", type=int)
    return jsonify(saldo_por_nif(nif, ano=ano))
