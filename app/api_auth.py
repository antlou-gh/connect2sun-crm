"""Autenticação da API de máquina (/api/v1).

A /api/v1 é governada SÓ por uma chave estática (X-API-Key), nunca pela sessão
de browser. A chave dá o menor privilégio possível: criar transações e ler
(clientes + transações). Ver require_login() em blueprints/auth.py.
"""

import secrets

from flask import current_app


def verificar_api_key(req) -> bool:
    """True se o header X-API-Key bate certo com MCP_API_KEY (config).

    Usa secrets.compare_digest para evitar timing attacks.
    Se MCP_API_KEY não estiver definida, devolve sempre False (fail-closed).
    """
    esperada = current_app.config.get("MCP_API_KEY")
    if not esperada:
        return False
    recebida = req.headers.get("X-API-Key", "")
    return secrets.compare_digest(recebida, esperada)
