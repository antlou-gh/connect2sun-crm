"""Autenticação da API de máquina (/api/v1).

A /api/v1 é governada SÓ por chave estática (X-API-Key), nunca pela sessão de
browser. Ver require_login() em blueprints/auth.py.

Duas chaves possíveis, cada uma com uma role:
- MCP_API_KEY          → "admin"        — ler, criar, editar.
- MCP_API_KEY_READONLY → "contabilista" — só ler (mesma restrição do login
  humano da contabilista: nunca escreve dados financeiros).
"""

import secrets

from flask import current_app


def role_da_chave(req) -> str | None:
    """ "admin", "contabilista" ou None, consoante a X-API-Key recebida.

    Fail-closed nos dois casos: se uma das chaves não estiver configurada
    (string vazia/None), essa role nunca é atribuída — não há valor por
    omissão adivinhável.

    Avalia sempre as duas comparações (com secrets.compare_digest, para não
    haver timing attack), antes de decidir — mesma disciplina do login em
    blueprints/auth.py.
    """
    recebida = req.headers.get("X-API-Key", "")
    chave_admin = current_app.config.get("MCP_API_KEY") or ""
    chave_readonly = current_app.config.get("MCP_API_KEY_READONLY") or ""

    bate_admin = bool(chave_admin) and secrets.compare_digest(recebida, chave_admin)
    bate_readonly = bool(chave_readonly) and secrets.compare_digest(recebida, chave_readonly)

    if bate_admin:
        return "admin"
    if bate_readonly:
        return "contabilista"
    return None


def verificar_api_key(req) -> bool:
    """True se a X-API-Key recebida corresponder a alguma chave válida.

    Mantida por compatibilidade com quem só precisa de saber "está
    autenticado", sem se importar com a role (ex.: testes antigos).
    """
    return role_da_chave(req) is not None
