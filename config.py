import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _normalize_db_url(url):
    """Aceita as várias formas de URL de Postgres e força o driver psycopg3.

    Neon/Render/Supabase fornecem URLs como `postgres://...` ou
    `postgresql://...`; o SQLAlchemy 2.x precisa de `postgresql+psycopg://`.
    """
    if not url:
        return None
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-connect2sun")
    SQLALCHEMY_DATABASE_URI = _normalize_db_url(os.environ.get("DATABASE_URL")) or (
        f"sqlite:///{os.path.join(BASE_DIR, 'connect2sun.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # pool_pre_ping evita erros de ligação fechada em Postgres serverless (Neon).
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
