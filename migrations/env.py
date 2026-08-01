"""Ambiente do Alembic para o connect2sun-crm.

A URL da base de dados vem da configuração da app (portanto da variável de
ambiente DATABASE_URL, já normalizada em config.py para o driver psycopg3).
Não se define `sqlalchemy.url` no alembic.ini — assim não há risco de ficar
lá uma credencial de produção esquecida.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from app import create_app, db

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# A app é criada só para dar acesso à config e ao metadata dos modelos.
flask_app = create_app()
DATABASE_URL = flask_app.config["SQLALCHEMY_DATABASE_URI"]

target_metadata = db.metadata

# Schemas geridos pela plataforma, não pela aplicação. O `neon_auth` é criado
# pela funcionalidade Neon Auth; sem esta exclusão o autogenerate propunha
# apagá-lo por não existir nos modelos.
SCHEMAS_EXTERNOS = {"neon_auth"}


def include_object(objecto, nome, tipo, reflectido, comparar_a):
    return getattr(objecto, "schema", None) not in SCHEMAS_EXTERNOS


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        include_schemas=False,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            include_schemas=False,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
