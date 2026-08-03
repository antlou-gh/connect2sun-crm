"""Smoke test de todas as rotas registadas.

Não valida regras de negócio — valida que nenhuma rota rebenta com 500 e que
nenhuma fica acessível sem sessão por esquecimento. É deliberadamente
genérico: percorre o `url_map` em vez de listar caminhos à mão, por isso uma
rota nova entra automaticamente nos testes sem ninguém se lembrar de a
acrescentar aqui.

A cobertura é rasa por desenho. O valor está em apanhar o erro estúpido —
um `import` em falta, um template renomeado, um decorador de autenticação
esquecido numa rota nova.
"""

import pytest
from werkzeug.routing import IntegerConverter

from app import create_app
from app import db as _db

from .conftest import make_cliente

# Rotas legitimamente acessíveis sem sessão iniciada.
PUBLICAS = {"ping", "auth.login_page", "auth.login", "static"}

# A /api/v1 é de máquina: não usa sessão, é governada pela X-API-Key.
PREFIXO_API_MAQUINA = "api_v1."

# Endpoints com efeitos que não queremos disparar num smoke test.
EXCLUIDOS = {
    "static",  # servir ficheiros do disco não diz nada sobre a app
    "auth.logout",  # limparia a sessão a meio do próprio teste
    "clients.seed_clients",  # popula a base com dados de demonstração
}


class ConfigSmoke:
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = "test"
    APP_PASSWORD = "pw-admin"
    MCP_API_KEY = "chave-de-teste"
    TOTP_SECRET = None
    CONTAB_PASSWORD = None
    CONTAB_TOTP_SECRET = None


def _caminho(regra):
    """Constrói um caminho concreto, preenchendo os parâmetros da rota."""
    valores = {}
    for arg in regra.arguments:
        conversor = regra._converters[arg]
        valores[arg] = 1 if isinstance(conversor, IntegerConverter) else "x"
    return regra.build(valores, append_unknown=False)[1]


def _regras(app, metodo="GET"):
    saida = []
    for regra in app.url_map.iter_rules():
        if regra.endpoint in EXCLUIDOS or metodo not in regra.methods:
            continue
        saida.append((regra.endpoint, _caminho(regra)))
    return sorted(saida)


def _regras_escrita(app):
    saida = []
    for regra in app.url_map.iter_rules():
        if regra.endpoint in EXCLUIDOS:
            continue
        for metodo in sorted(regra.methods & {"POST", "PUT", "DELETE", "PATCH"}):
            saida.append((regra.endpoint, _caminho(regra), metodo))
    return sorted(saida)


# A app é criada uma vez ao carregar o módulo, só para gerar os parâmetros.
_app_para_ids = create_app(ConfigSmoke)
REGRAS_GET = _regras(_app_para_ids, "GET")
REGRAS_ESCRITA = _regras_escrita(_app_para_ids)


@pytest.fixture
def app_smoke():
    app = create_app(ConfigSmoke)
    with app.app_context():
        _db.create_all()
        # Um cliente com id=1, para as rotas com <int:client_id> terem
        # alguma coisa para encontrar em vez de darem sempre 404.
        make_cliente(_db, nif="123456789")
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def autenticado(app_smoke):
    cliente = app_smoke.test_client()
    with cliente.session_transaction() as sessao:
        sessao["authed"] = True
        sessao["role"] = "admin"
    return cliente


@pytest.mark.parametrize(("endpoint", "caminho"), REGRAS_GET, ids=[e for e, _ in REGRAS_GET])
def test_get_nao_rebenta(autenticado, endpoint, caminho):
    """Nenhuma rota GET pode devolver 5xx.

    4xx é aceitável: um id inventado dá 404, uma rota de máquina dá 401.
    O que não pode acontecer é a app estoirar.
    """
    resposta = autenticado.get(caminho)
    assert resposta.status_code < 500, (
        f"{endpoint} ({caminho}) devolveu {resposta.status_code}\n"
        f"{resposta.get_data(as_text=True)[:400]}"
    )


@pytest.mark.parametrize(("endpoint", "caminho"), REGRAS_GET, ids=[e for e, _ in REGRAS_GET])
def test_get_esta_protegido(app_smoke, endpoint, caminho):
    """Nenhuma rota nova pode ficar aberta sem sessão por esquecimento.

    Sem sessão, uma rota tem de redireccionar (302) ou recusar (401/403).
    Um 200 aqui significa que há conteúdo a sair para quem não fez login.
    """
    if endpoint in PUBLICAS or endpoint.startswith(PREFIXO_API_MAQUINA):
        pytest.skip("rota pública ou de máquina")

    resposta = app_smoke.test_client().get(caminho)
    assert resposta.status_code != 200, f"{endpoint} ({caminho}) devolveu 200 sem sessão iniciada"
    assert resposta.status_code in (302, 401, 403), (
        f"{endpoint} ({caminho}) devolveu {resposta.status_code}, esperado 302/401/403"
    )


@pytest.mark.parametrize(
    ("endpoint", "caminho", "metodo"),
    REGRAS_ESCRITA,
    ids=[f"{m.lower()}-{e}" for e, _, m in REGRAS_ESCRITA],
)
def test_escrita_esta_protegida(app_smoke, endpoint, caminho, metodo):
    """Nenhuma rota de escrita pode aceitar pedidos sem sessão.

    Mais importante que o equivalente em GET: aqui um esquecimento não expõe
    dados, permite alterá-los. O pedido é rejeitado antes de chegar à vista,
    por isso não tem efeitos secundários.
    """
    if endpoint.startswith(PREFIXO_API_MAQUINA) or endpoint in PUBLICAS:
        pytest.skip("rota pública ou de máquina")

    resposta = getattr(app_smoke.test_client(), metodo.lower())(caminho, json={})
    assert resposta.status_code in (302, 401, 403), (
        f"{metodo} {caminho} ({endpoint}) devolveu {resposta.status_code} sem sessão"
    )


def test_rotas_publicas_respondem(app_smoke):
    """Contraprova: as que devem ser públicas continuam a sê-lo."""
    cliente = app_smoke.test_client()
    assert cliente.get("/ping").status_code == 200
    assert cliente.get("/login").status_code == 200


def test_o_mapa_de_rotas_nao_encolheu():
    """Se alguém acrescentar uma rota, ela entra nos testes sozinha.

    Este número é uma sentinela: se cair, alguém removeu rotas e convém
    reparar nisso em vez de descobrir por acaso.
    """
    assert len(REGRAS_GET) >= 25, f"só {len(REGRAS_GET)} rotas GET encontradas"
    assert len(REGRAS_ESCRITA) >= 15, f"só {len(REGRAS_ESCRITA)} rotas de escrita"
