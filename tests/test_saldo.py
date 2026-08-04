"""Testes do saldo agregado por NIF (`saldo_por_nif` + GET /api/v1/saldo).

O que se está a proteger, por ordem de importância:
  1. NIF desconhecido não pode parecer um saldo de zero;
  2. a soma tem de vir da BD e cobrir TODOS os movimentos — o servidor MCP
     trunca a listagem às 100 linhas, e foi esse o motivo de existir isto;
  3. NIFs gravados em formatos diferentes ("PT123...", com espaços, inteiro
     do Excel) têm de resolver para o mesmo cliente.
"""

from datetime import date

from app.financeiro_service import saldo_por_nif

from .conftest import make_cliente, make_transacao

CHAVE = {"X-API-Key": "test-key"}


def _movimentos(db, cliente, especificacoes):
    """especificacoes: lista de (valor, estado[, data])."""
    for espec in especificacoes:
        valor, estado = espec[0], espec[1]
        data = espec[2] if len(espec) > 2 else date(2026, 1, 1)
        make_transacao(
            db,
            cliente_id=cliente.id,
            valor=valor,
            estado=estado,
            data=data,
            tipo_movimento="Facturação",
            entidade_emissora="Entidade Teste",
        )


# ── A distinção que motiva a função ──────────────────────────────────────────


def test_nif_desconhecido_nao_e_saldo_zero(app, db):
    """O erro que isto existe para evitar: 0,00 € a passar por 'está saldado'."""
    r = saldo_por_nif("999999999")
    assert r["encontrado"] is False
    assert r["clientes"] == []
    assert r["motivo"] == "Nenhum cliente com este NIF."


def test_cliente_sem_movimentos_e_encontrado_com_saldo_zero(app, db):
    make_cliente(db, client_number=1, nif="123456789")
    r = saldo_por_nif("123456789")
    assert r["encontrado"] is True
    assert r["saldo"] == 0.0
    assert r["total_movimentos"] == 0
    assert r["primeira_data"] is None


def test_nif_vazio_nao_estoira(app, db):
    r = saldo_por_nif("   ")
    assert r["encontrado"] is False
    assert r["nif"] is None


# ── A soma ───────────────────────────────────────────────────────────────────


def test_saldo_soma_valores_com_sinal(app, db):
    c = make_cliente(db, client_number=1, nif="123456789")
    _movimentos(db, c, [(1000.0, "Fechado"), (-250.0, "Fechado"), (-100.5, "Falta pagar")])
    r = saldo_por_nif("123456789")
    assert r["saldo"] == 649.5
    assert r["total_movimentos"] == 3


def test_soma_todos_os_movimentos_mesmo_acima_das_100_linhas(app, db):
    """O motivo de existir o endpoint: somar do lado do cliente perderia as
    linhas cortadas pelo limite de 100 da listagem do MCP."""
    c = make_cliente(db, client_number=1, nif="123456789")
    _movimentos(db, c, [(1.0, "Fechado")] * 150)
    r = saldo_por_nif("123456789")
    assert r["total_movimentos"] == 150
    assert r["saldo"] == 150.0  # não 100.0


def test_em_aberto_exclui_fechados(app, db):
    c = make_cliente(db, client_number=1, nif="123456789")
    _movimentos(
        db,
        c,
        [
            (1000.0, "Fechado"),
            (300.0, "Falta receber"),
            (-50.0, "Falta pagar"),
            (20.0, "Pag. Parcial"),
        ],
    )
    r = saldo_por_nif("123456789")
    assert r["saldo"] == 1270.0
    assert r["em_aberto"] == 270.0


def test_movimento_sem_estado_nao_conta_como_em_aberto(app, db):
    """Sem estado preenchido não se assume que esteja por liquidar — aparece
    no detalhe, mas fora do `em_aberto`."""
    c = make_cliente(db, client_number=1, nif="123456789")
    _movimentos(db, c, [(500.0, None), (100.0, "Falta receber")])
    r = saldo_por_nif("123456789")
    assert r["saldo"] == 600.0
    assert r["em_aberto"] == 100.0
    assert any(linha["estado"] is None for linha in r["por_estado"])


# ── Isolamento e filtros ─────────────────────────────────────────────────────


def test_nao_mistura_movimentos_de_outro_cliente(app, db):
    a = make_cliente(db, client_number=1, nif="123456789")
    b = make_cliente(db, client_number=2, nif="987654321")
    _movimentos(db, a, [(100.0, "Fechado")])
    _movimentos(db, b, [(9999.0, "Fechado")])
    assert saldo_por_nif("123456789")["saldo"] == 100.0


def test_ignora_movimentos_sem_cliente(app, db):
    c = make_cliente(db, client_number=1, nif="123456789")
    _movimentos(db, c, [(100.0, "Fechado")])
    make_transacao(
        db,
        cliente_id=None,
        valor=5000.0,
        estado="Fechado",
        tipo_movimento="Facturação",
        entidade_emissora="Entidade Teste",
    )
    assert saldo_por_nif("123456789")["saldo"] == 100.0


def test_filtro_por_ano(app, db):
    c = make_cliente(db, client_number=1, nif="123456789")
    _movimentos(
        db,
        c,
        [(100.0, "Fechado", date(2026, 5, 2)), (700.0, "Fechado", date(2025, 5, 2))],
    )
    assert saldo_por_nif("123456789")["saldo"] == 800.0
    assert saldo_por_nif("123456789", ano=2026)["saldo"] == 100.0
    assert saldo_por_nif("123456789", ano=2026)["primeira_data"] == "2026-05-02"


# ── Normalização do NIF (formatos herdados do Excel) ─────────────────────────


def test_nif_gravado_com_prefixo_pt_e_encontrado(app, db):
    c = make_cliente(db, client_number=1, nif="PT123456789")
    _movimentos(db, c, [(100.0, "Fechado")])
    assert saldo_por_nif("123456789")["saldo"] == 100.0
    assert saldo_por_nif("PT123456789")["encontrado"] is True


def test_nif_com_espacos_e_encontrado(app, db):
    make_cliente(db, client_number=1, nif="123 456 789")
    assert saldo_por_nif("123456789")["encontrado"] is True


def test_dois_clientes_com_o_mesmo_nif_somam_e_aparecem_ambos(app, db):
    """Acontece quando o mesmo contribuinte tem duas fichas. Somar os dois é
    melhor do que escolher um em silêncio — e a lista de clientes devolvida
    deixa a ambiguidade à vista."""
    a = make_cliente(db, client_number=1, nif="123456789", email="a@example.com")
    b = make_cliente(db, client_number=2, nif="123456789", email="b@example.com")
    _movimentos(db, a, [(100.0, "Fechado")])
    _movimentos(db, b, [(50.0, "Fechado")])
    r = saldo_por_nif("123456789")
    assert r["saldo"] == 150.0
    assert len(r["clientes"]) == 2


# ── Endpoint HTTP ────────────────────────────────────────────────────────────


def test_endpoint_exige_chave(app, db):
    assert app.test_client().get("/api/v1/saldo?nif=123456789").status_code == 401


def test_endpoint_exige_nif(app, db):
    r = app.test_client().get("/api/v1/saldo", headers=CHAVE)
    assert r.status_code == 400
    assert "nif" in r.get_json()["error"].lower()


def test_endpoint_devolve_os_totais(app, db):
    c = make_cliente(db, client_number=1, nif="123456789", name="Cliente Um")
    _movimentos(db, c, [(1000.0, "Fechado"), (250.0, "Falta receber")])
    r = app.test_client().get("/api/v1/saldo?nif=123456789", headers=CHAVE)
    assert r.status_code == 200
    dados = r.get_json()
    assert dados["saldo"] == 1250.0
    assert dados["em_aberto"] == 250.0
    assert dados["clientes"][0]["name"] == "Cliente Um"


def test_endpoint_nif_desconhecido_da_200_e_nao_404(app, db):
    """200 com `encontrado: false` — um 404 obrigaria quem chama a adivinhar se
    foi o NIF que não existe ou o endpoint que desapareceu."""
    r = app.test_client().get("/api/v1/saldo?nif=999999999", headers=CHAVE)
    assert r.status_code == 200
    assert r.get_json()["encontrado"] is False


def test_endpoint_aceita_filtro_de_ano(app, db):
    c = make_cliente(db, client_number=1, nif="123456789")
    _movimentos(db, c, [(100.0, "Fechado", date(2026, 5, 2)), (700.0, "Fechado", date(2025, 5, 2))])
    r = app.test_client().get("/api/v1/saldo?nif=123456789&ano=2026", headers=CHAVE)
    assert r.get_json()["saldo"] == 100.0
