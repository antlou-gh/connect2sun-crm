"""Testes à autenticação e à separação de perfis.

O foco é a barreira do `require_login()` em `app/blueprints/auth.py`. O acesso
read-only da contabilista é garantido apenas por lógica de código — não há nada
na base de dados a impedi-la de escrever. Se essa lógica quebrar numa
refactorização, ela passa a poder alterar dados financeiros sem que nada avise.
Estes testes são a única rede a cobrir isso.
"""

import pyotp
import pytest

from app import create_app
from app import db as _db

SEGREDO_ADMIN = pyotp.random_base32()
SEGREDO_CONTAB = pyotp.random_base32()


class ConfigBase:
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = "test"
    MCP_API_KEY = "chave-de-teste"
    MCP_API_KEY_READONLY = "chave-de-teste-readonly"
    APP_PASSWORD = "pw-admin"
    CONTAB_PASSWORD = None
    TOTP_SECRET = None
    CONTAB_TOTP_SECRET = None


class ConfigSemMfa(ConfigBase):
    """Modo dev local: admin entra só com password."""


class ConfigComMfa(ConfigBase):
    CONTAB_PASSWORD = "pw-contab"
    TOTP_SECRET = SEGREDO_ADMIN
    CONTAB_TOTP_SECRET = SEGREDO_CONTAB


def _cliente(config):
    app = create_app(config)
    with app.app_context():
        _db.create_all()
        yield app.test_client()
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def cliente_sem_mfa():
    yield from _cliente(ConfigSemMfa)


@pytest.fixture
def cliente_com_mfa():
    yield from _cliente(ConfigComMfa)


def _entrar_como(cliente, role):
    """Força uma sessão autenticada, sem passar pelo fluxo de login."""
    with cliente.session_transaction() as sessao:
        sessao["authed"] = True
        sessao["role"] = role


# ── Sem sessão ────────────────────────────────────────────────────────────────


def test_pagina_exige_login(cliente_sem_mfa):
    r = cliente_sem_mfa.get("/")
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]


def test_api_sem_sessao_devolve_401(cliente_sem_mfa):
    r = cliente_sem_mfa.get("/api/clients/")
    assert r.status_code == 401
    assert r.is_json


def test_ping_e_publico(cliente_sem_mfa):
    assert cliente_sem_mfa.get("/ping").status_code == 200


# ── Login ─────────────────────────────────────────────────────────────────────


def test_password_errada_devolve_401(cliente_sem_mfa):
    r = cliente_sem_mfa.post("/login", data={"password": "errada"})
    assert r.status_code == 401


def test_password_vazia_nao_entra(cliente_sem_mfa):
    """Uma config sem password definida não pode virar porta aberta."""
    r = cliente_sem_mfa.post("/login", data={"password": ""})
    assert r.status_code == 401


def test_admin_entra_sem_mfa_quando_nao_configurado(cliente_sem_mfa):
    r = cliente_sem_mfa.post("/login", data={"password": "pw-admin"})
    assert r.status_code == 302
    with cliente_sem_mfa.session_transaction() as sessao:
        assert sessao["authed"] is True
        assert sessao["role"] == "admin"


def test_password_certa_com_mfa_nao_autentica_logo(cliente_com_mfa):
    """Com MFA configurado, a password sozinha não dá sessão autenticada."""
    r = cliente_com_mfa.post("/login", data={"password": "pw-admin"})
    assert r.status_code == 302
    assert "/mfa" in r.headers["Location"]
    with cliente_com_mfa.session_transaction() as sessao:
        assert not sessao.get("authed")
        assert sessao.get("pw_verified") is True


def test_codigo_mfa_errado_nao_autentica(cliente_com_mfa):
    cliente_com_mfa.post("/login", data={"password": "pw-admin"})
    r = cliente_com_mfa.post("/mfa", data={"code": "000000"})
    assert r.status_code == 401
    with cliente_com_mfa.session_transaction() as sessao:
        assert not sessao.get("authed")


def test_codigo_mfa_certo_autentica(cliente_com_mfa):
    cliente_com_mfa.post("/login", data={"password": "pw-admin"})
    codigo = pyotp.TOTP(SEGREDO_ADMIN).now()
    r = cliente_com_mfa.post("/mfa", data={"code": codigo})
    assert r.status_code == 302
    with cliente_com_mfa.session_transaction() as sessao:
        assert sessao["authed"] is True
        assert sessao["role"] == "admin"


def test_mfa_sem_passar_pela_password_e_recusado(cliente_com_mfa):
    """Não se salta o primeiro fator indo directo ao /mfa."""
    codigo = pyotp.TOTP(SEGREDO_ADMIN).now()
    r = cliente_com_mfa.post("/mfa", data={"code": codigo})
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]
    with cliente_com_mfa.session_transaction() as sessao:
        assert not sessao.get("authed")


def test_contabilista_sem_mfa_configurado_nao_entra(cliente_sem_mfa):
    """MFA é obrigatório para a contabilista, sem atalho de dev."""
    app = create_app(ConfigSemMfa)
    app.config["CONTAB_PASSWORD"] = "pw-contab"
    with app.app_context():
        _db.create_all()
        c = app.test_client()
        r = c.post("/login", data={"password": "pw-contab"})
        assert r.status_code == 401
        with c.session_transaction() as sessao:
            assert not sessao.get("authed")
        _db.drop_all()


def test_contabilista_entra_com_o_seu_proprio_totp(cliente_com_mfa):
    cliente_com_mfa.post("/login", data={"password": "pw-contab"})
    codigo = pyotp.TOTP(SEGREDO_CONTAB).now()
    r = cliente_com_mfa.post("/mfa", data={"code": codigo})
    assert r.status_code == 302
    with cliente_com_mfa.session_transaction() as sessao:
        assert sessao["role"] == "contabilista"


def test_totp_do_admin_nao_serve_a_contabilista(cliente_com_mfa):
    """Os dois perfis têm segredos distintos e não são intermutáveis."""
    cliente_com_mfa.post("/login", data={"password": "pw-contab"})
    r = cliente_com_mfa.post("/mfa", data={"code": pyotp.TOTP(SEGREDO_ADMIN).now()})
    assert r.status_code == 401


# ── Perfil contabilista: read-only ────────────────────────────────────────────


def test_contabilista_le_o_financeiro(cliente_com_mfa):
    _entrar_como(cliente_com_mfa, "contabilista")
    assert cliente_com_mfa.get("/financeiro").status_code == 200
    assert cliente_com_mfa.get("/api/financeiro/transacoes").status_code == 200
    assert cliente_com_mfa.get("/api/financeiro/meta").status_code == 200


@pytest.mark.parametrize(
    ("metodo", "caminho"),
    [
        ("post", "/api/financeiro/transacoes"),
        ("put", "/api/financeiro/transacoes/1"),
        ("delete", "/api/financeiro/transacoes/1"),
    ],
)
def test_contabilista_nao_escreve_no_financeiro(cliente_com_mfa, metodo, caminho):
    """O coração desta feature: leitura sim, escrita nunca."""
    _entrar_como(cliente_com_mfa, "contabilista")
    r = getattr(cliente_com_mfa, metodo)(caminho, json={})
    assert r.status_code == 403, f"{metodo.upper()} {caminho} devolveu {r.status_code}"


@pytest.mark.parametrize(
    "caminho",
    ["/api/clients/", "/api/clients/1", "/api/financeiro/dashboard/pl"],
)
def test_contabilista_nao_ve_fora_do_seu_ambito(cliente_com_mfa, caminho):
    _entrar_como(cliente_com_mfa, "contabilista")
    assert cliente_com_mfa.get(caminho).status_code == 403


def test_admin_escreve_onde_a_contabilista_nao(cliente_com_mfa):
    """Contraprova: as rotas acima não estão bloqueadas para toda a gente."""
    _entrar_como(cliente_com_mfa, "admin")
    r = cliente_com_mfa.get("/api/clients/")
    assert r.status_code == 200


def test_role_desconhecido_falha_fechado(cliente_com_mfa):
    """Uma sessão com role corrompido é limpa, não promovida."""
    _entrar_como(cliente_com_mfa, "qualquer-coisa")
    r = cliente_com_mfa.get("/")
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]
    with cliente_com_mfa.session_transaction() as sessao:
        assert not sessao.get("authed")


def test_logout_limpa_a_sessao(cliente_com_mfa):
    _entrar_como(cliente_com_mfa, "admin")
    cliente_com_mfa.get("/logout")
    with cliente_com_mfa.session_transaction() as sessao:
        assert not sessao.get("authed")


# ── API de máquina (/api/v1) ──────────────────────────────────────────────────


def test_api_v1_exige_chave(cliente_sem_mfa):
    assert cliente_sem_mfa.get("/api/v1/clientes").status_code == 401


def test_api_v1_aceita_a_chave(cliente_sem_mfa):
    r = cliente_sem_mfa.get("/api/v1/clientes", headers={"X-API-Key": "chave-de-teste"})
    assert r.status_code == 200


def test_sessao_de_browser_nao_abre_a_api_v1(cliente_com_mfa):
    """A /api/v1 é governada só pela chave — estar autenticado não basta."""
    _entrar_como(cliente_com_mfa, "admin")
    assert cliente_com_mfa.get("/api/v1/clientes").status_code == 401


# ── Roles na api/v1: MCP_API_KEY (admin) vs MCP_API_KEY_READONLY (contabilista) ─
# A contabilista não pode editar transações por nenhum caminho — nem o
# formulário humano (já coberto acima), nem a API de máquina. Estes testes são
# a rede que garante isso também do lado do MCP.


def _criar_transacao_admin(cliente):
    """Cria um movimento com a chave admin; devolve o id. Ajuda os testes de
    PATCH a não dependerem de haver dados pré-existentes."""
    r = cliente.post(
        "/api/v1/transacoes",
        headers={"X-API-Key": "chave-de-teste"},
        json={
            "descricao": "Movimento de teste",
            "valor": 100.0,
            "data": "2026-01-01",
            "entidade_emissora": "Fornecedor Teste",
        },
    )
    assert r.status_code == 201, r.get_data(as_text=True)
    return r.get_json()["id"]


def test_api_v1_chave_readonly_le_mas_nao_cria(cliente_sem_mfa):
    r_get = cliente_sem_mfa.get(
        "/api/v1/clientes", headers={"X-API-Key": "chave-de-teste-readonly"}
    )
    assert r_get.status_code == 200

    r_post = cliente_sem_mfa.post(
        "/api/v1/transacoes",
        headers={"X-API-Key": "chave-de-teste-readonly"},
        json={"descricao": "x", "valor": 1.0, "data": "2026-01-01", "entidade_emissora": "x"},
    )
    assert r_post.status_code == 403


def test_api_v1_patch_com_chave_admin_funciona(cliente_sem_mfa):
    id_transacao = _criar_transacao_admin(cliente_sem_mfa)
    r = cliente_sem_mfa.patch(
        f"/api/v1/transacoes/{id_transacao}",
        headers={"X-API-Key": "chave-de-teste"},
        json={"valor": 200.0},
    )
    assert r.status_code == 200
    assert r.get_json()["valor"] == 200.0


def test_api_v1_patch_com_chave_readonly_da_403(cliente_sem_mfa):
    id_transacao = _criar_transacao_admin(cliente_sem_mfa)
    r = cliente_sem_mfa.patch(
        f"/api/v1/transacoes/{id_transacao}",
        headers={"X-API-Key": "chave-de-teste-readonly"},
        json={"valor": 200.0},
    )
    assert r.status_code == 403


def test_api_v1_chave_readonly_por_configurar_nunca_bate_certo(cliente_com_mfa):
    """ConfigComMfa não define MCP_API_KEY_READONLY (fica None) — sem chave
    configurada, nenhum X-API-Key deve poder passar-se por essa role."""
    r = cliente_com_mfa.get("/api/v1/clientes", headers={"X-API-Key": ""})
    assert r.status_code == 401
