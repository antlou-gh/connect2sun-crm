"""Testes do PATCH /api/v1/transacoes/<id> (edição parcial de movimentos).

Cobre `financeiro_service.atualizar_transacao_from_dict` (a regra) e o
endpoint em `blueprints/api_v1.py` (o transporte HTTP — status codes,
autenticação). A role "admin" vs "contabilista" já está coberta em
test_auth.py; aqui assume-se sempre a chave admin, para focar nas regras de
validação do PATCH em si.
"""

import pytest

from app.financeiro_service import atualizar_transacao_from_dict

from .conftest import make_cliente, make_transacao

CHAVE = {"X-API-Key": "test-key"}


# ── financeiro_service.atualizar_transacao_from_dict (nível de função) ───────


def test_patch_um_campo_aplica_e_nao_mexe_no_resto(app, db):
    t = make_transacao(db, valor=100.0, tipo_movimento="Facturação", descricao="Original")
    _, erros, avisos = atualizar_transacao_from_dict(t, {"valor": 250.0})
    assert erros == []
    assert avisos == []
    assert t.valor == 250.0
    assert t.descricao == "Original"  # não tocado


def test_iva_recalculado_quando_valor_muda_sem_iva_explicito(app, db):
    t = make_transacao(
        db, valor=-436.50, valor_siva=-349.20, iva=0.0, tipo_movimento="Custos gerais"
    )
    _, erros, avisos = atualizar_transacao_from_dict(t, {"valor": -436.50})
    assert erros == []
    assert t.iva == pytest.approx(87.30)
    assert avisos == []  # IVA deu positivo — sem aviso a dar


def test_iva_recalculado_quando_so_valor_siva_muda(app, db):
    t = make_transacao(
        db, valor=-436.50, valor_siva=-300.0, iva=0.0, tipo_movimento="Custos gerais"
    )
    _, erros, _ = atualizar_transacao_from_dict(t, {"valor_siva": -349.20})
    assert erros == []
    assert t.iva == pytest.approx(87.30)


def test_iva_explicito_prevalece_sobre_o_recalculo(app, db):
    """Caso royalties: retenção na fonte dá IVA negativo por regra de negócio
    — se vier explícito no mesmo pedido, não é substituído pelo cálculo."""
    t = make_transacao(
        db, valor=-1000.0, valor_siva=-1000.0, iva=0.0, tipo_movimento="Custos gerais"
    )
    _, erros, avisos = atualizar_transacao_from_dict(t, {"valor": -800.0, "iva": -50.0})
    assert erros == []
    assert t.iva == -50.0
    assert avisos == []  # o aviso de IVA negativo só se aplica ao recálculo automático


def test_iva_recalculado_negativo_avisa_mas_nao_bloqueia(app, db):
    t = make_transacao(db, valor=-100.0, valor_siva=-100.0, iva=0.0, tipo_movimento="Custos gerais")
    # valor_siva (-150) maior em magnitude que o novo valor (-100) ⇒ IVA < 0.
    _, erros, avisos = atualizar_transacao_from_dict(t, {"valor_siva": -150.0})
    assert erros == []
    assert t.iva == pytest.approx(-50.0)
    assert len(avisos) == 1
    assert "negativo" in avisos[0]


def test_numero_ordem_no_corpo_e_erro(app, db):
    t = make_transacao(db, valor=100.0, tipo_movimento="Facturação", numero_ordem=7)
    # Acompanhado de um campo válido (valor) — sem isto, "nenhum campo
    # editável reconhecido" já rejeitaria o pedido por outra razão, e o
    # teste passaria mesmo que a guarda de imutabilidade estivesse partida.
    _, erros, _ = atualizar_transacao_from_dict(t, {"numero_ordem": 8, "valor": 5.0})
    assert erros
    assert t.numero_ordem == 7  # não foi alterado
    assert t.valor == 100.0  # rejeitado por inteiro, mesmo o campo válido


def test_id_no_corpo_e_erro(app, db):
    t = make_transacao(db, valor=100.0, tipo_movimento="Facturação")
    _, erros, _ = atualizar_transacao_from_dict(t, {"id": 999, "valor": 5.0})
    assert erros
    assert t.valor == 100.0  # rejeitado por inteiro, mesmo o campo válido


def test_entidade_emissora_vazia_e_erro(app, db):
    t = make_transacao(db, valor=100.0, tipo_movimento="Facturação", entidade_emissora="Original")
    _, erros, _ = atualizar_transacao_from_dict(t, {"entidade_emissora": ""})
    assert erros
    assert t.entidade_emissora == "Original"


def test_entidade_emissora_null_e_erro(app, db):
    t = make_transacao(db, valor=100.0, tipo_movimento="Facturação", entidade_emissora="Original")
    _, erros, _ = atualizar_transacao_from_dict(t, {"entidade_emissora": None})
    assert erros


def test_entidade_emissora_ausente_do_corpo_nao_e_tocada(app, db):
    t = make_transacao(db, valor=100.0, tipo_movimento="Facturação", entidade_emissora="Original")
    _, erros, _ = atualizar_transacao_from_dict(t, {"valor": 5.0})
    assert erros == []
    assert t.entidade_emissora == "Original"


@pytest.mark.parametrize("campo,valor", [("estado", "Inventado"), ("tipo_movimento", "Inventado")])
def test_enum_fechado_fora_da_lista_e_erro(app, db, campo, valor):
    t = make_transacao(db, valor=100.0, tipo_movimento="Facturação")
    _, erros, _ = atualizar_transacao_from_dict(t, {campo: valor})
    assert erros


def test_categoria_fora_da_lista_e_erro(app, db):
    t = make_transacao(db, valor=100.0, tipo_movimento="Facturação")
    _, erros, _ = atualizar_transacao_from_dict(t, {"categoria": "Inventada"})
    assert erros


def test_categoria_null_e_permitida(app, db):
    t = make_transacao(db, valor=100.0, tipo_movimento="Facturação", categoria="Estrutura")
    _, erros, _ = atualizar_transacao_from_dict(t, {"categoria": None})
    assert erros == []
    assert t.categoria is None


def test_cliente_id_inexistente_e_erro(app, db):
    t = make_transacao(db, valor=100.0, tipo_movimento="Facturação")
    _, erros, _ = atualizar_transacao_from_dict(t, {"cliente_id": 999999})
    assert erros


def test_cliente_id_null_desassocia(app, db):
    cliente = make_cliente(db, nif="123456789")
    t = make_transacao(db, valor=100.0, tipo_movimento="Facturação", cliente_id=cliente.id)
    _, erros, _ = atualizar_transacao_from_dict(t, {"cliente_id": None})
    assert erros == []
    assert t.cliente_id is None


def test_corpo_vazio_e_erro(app, db):
    t = make_transacao(db, valor=100.0, tipo_movimento="Facturação")
    _, erros, _ = atualizar_transacao_from_dict(t, {})
    assert erros


def test_corpo_sem_campos_reconhecidos_e_erro(app, db):
    t = make_transacao(db, valor=100.0, tipo_movimento="Facturação")
    _, erros, _ = atualizar_transacao_from_dict(t, {"campo_que_nao_existe": 1})
    assert erros


# ── Endpoint HTTP (transporte, status codes) ──────────────────────────────────


def test_endpoint_patch_caminho_feliz(app, db, client):
    t = make_transacao(db, valor=100.0, tipo_movimento="Facturação", entidade_emissora="X")
    r = client.patch(f"/api/v1/transacoes/{t.id}", headers=CHAVE, json={"valor": 42.0})
    assert r.status_code == 200
    corpo = r.get_json()
    assert corpo["valor"] == 42.0
    assert corpo["id"] == t.id


def test_endpoint_patch_id_inexistente_da_404(app, db, client):
    r = client.patch("/api/v1/transacoes/999999", headers=CHAVE, json={"valor": 1.0})
    assert r.status_code == 404


def test_endpoint_patch_sem_chave_da_401(app, db, client):
    t = make_transacao(db, valor=100.0, tipo_movimento="Facturação")
    r = client.patch(f"/api/v1/transacoes/{t.id}", json={"valor": 1.0})
    assert r.status_code == 401


def test_endpoint_patch_corpo_invalido_da_400_e_nao_persiste(app, db, client):
    t = make_transacao(db, valor=100.0, tipo_movimento="Facturação")
    r = client.patch(f"/api/v1/transacoes/{t.id}", headers=CHAVE, json={"numero_ordem": 5})
    assert r.status_code == 400
    # a alteração rejeitada não pode ter ficado meio-aplicada na BD
    from app.models import Transacao

    recarregada = db.session.get(Transacao, t.id)
    assert recarregada.numero_ordem != 5


def test_endpoint_patch_aviso_de_iva_negativo_viaja_na_resposta(app, db, client):
    t = make_transacao(db, valor=-100.0, valor_siva=-100.0, tipo_movimento="Custos gerais")
    r = client.patch(f"/api/v1/transacoes/{t.id}", headers=CHAVE, json={"valor_siva": -150.0})
    assert r.status_code == 200
    corpo = r.get_json()
    assert "avisos" in corpo
    assert len(corpo["avisos"]) == 1


# ── Regressão manual: movimento nº313 (retenção na fonte) ────────────────────
# Corrigido à mão na app em 05/08/2026; este teste replica o mesmo PATCH que
# teria evitado a intervenção manual, garantindo que produz o mesmo resultado.


def test_regressao_movimento_313_retencao_na_fonte(app, db, client):
    t = make_transacao(
        db,
        numero_ordem=313,
        valor=-1000.0,
        valor_siva=-1000.0,
        iva=0.0,
        tipo_movimento="Custos gerais",
        entidade_emissora="SunEnergy",
        categoria="Royalties",
    )
    # Retenção na fonte: valor pago fica abaixo da base, IVA vem explícito
    # (negativo por regra de negócio) para não ser sobreposto pelo recálculo.
    r = client.patch(
        f"/api/v1/transacoes/{t.id}",
        headers=CHAVE,
        json={"valor": -850.0, "iva": -150.0},
    )
    assert r.status_code == 200
    corpo = r.get_json()
    assert corpo["valor"] == -850.0
    assert corpo["iva"] == -150.0
    assert "avisos" not in corpo
