from app.blueprints.financeiro import _margem_cliente
from .conftest import make_cliente, make_transacao


def test_margem_cliente_so_facturas(app, db):
    """Comportamento inalterado: sem NC, margem = facturação − custos."""
    c = make_cliente(db)
    make_transacao(db, cliente_id=c.id, valor=1000.0, tipo_movimento="Facturação")
    make_transacao(db, cliente_id=c.id, valor=-200.0, tipo_movimento="Material/Serviços")

    faturacao, custos, margem = _margem_cliente(c.id)

    assert faturacao == 1000.0
    assert custos == 200.0
    assert margem == 800.0


def test_margem_cliente_com_nota_credito_de_venda(app, db):
    """NC negativa (venda anulada) abate à facturação — caso André Nóvoa."""
    c = make_cliente(db)
    make_transacao(db, cliente_id=c.id, valor=3082.38, tipo_movimento="Facturação")
    make_transacao(db, cliente_id=c.id, valor=3082.38, tipo_movimento="Facturação")
    make_transacao(db, cliente_id=c.id, valor=-3082.38, tipo_movimento="Nota de crédito")
    make_transacao(db, cliente_id=c.id, valor=-896.28, tipo_movimento="Material/Serviços")

    faturacao, custos, margem = _margem_cliente(c.id)

    assert faturacao == 3082.38
    assert custos == 896.28
    assert margem == 2186.10


def test_margem_cliente_com_nota_credito_de_fornecedor(app, db):
    """NC positiva (de fornecedor) abate aos custos, não à facturação."""
    c = make_cliente(db)
    make_transacao(db, cliente_id=c.id, valor=1000.0, tipo_movimento="Facturação")
    make_transacao(db, cliente_id=c.id, valor=-500.0, tipo_movimento="Material/Serviços")
    make_transacao(db, cliente_id=c.id, valor=150.0, tipo_movimento="Nota de crédito")

    faturacao, custos, margem = _margem_cliente(c.id)

    assert faturacao == 1000.0
    assert custos == 350.0
    assert margem == 650.0
