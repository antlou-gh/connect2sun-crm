from datetime import date

import pytest

from app import create_app, db as _db
from app.models import Client, Transacao


class TestConfig:
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = "test"
    APP_PASSWORD = "test"
    TOTP_SECRET = None
    MCP_API_KEY = "test-key"


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        yield app


@pytest.fixture
def db(app):
    return _db


def make_cliente(db, **kwargs):
    n = kwargs.pop("client_number", 1)
    c = Client(
        client_number=n,
        name=kwargs.pop("name", f"Cliente {n}"),
        email=kwargs.pop("email", f"cliente{n}@example.com"),
        **kwargs,
    )
    db.session.add(c)
    db.session.commit()
    return c


def make_transacao(db, cliente_id=None, **kwargs):
    t = Transacao(
        descricao=kwargs.pop("descricao", "Movimento"),
        valor=kwargs.pop("valor"),
        data=kwargs.pop("data", date(2026, 1, 1)),
        tipo_movimento=kwargs.pop("tipo_movimento"),
        cliente_id=cliente_id,
        **kwargs,
    )
    db.session.add(t)
    db.session.commit()
    return t
