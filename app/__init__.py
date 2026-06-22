from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from config import Config

db = SQLAlchemy()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)

    from .blueprints.clients import bp as clients_bp
    from .blueprints.installations import bp as installations_bp
    from .blueprints.interactions import bp as interactions_bp
    from .blueprints.proposals import bp as proposals_bp
    from .blueprints.frontend import bp as frontend_bp
    from .blueprints.auth import bp as auth_bp, require_login

    app.register_blueprint(clients_bp, url_prefix="/api/clients")
    app.register_blueprint(installations_bp, url_prefix="/api/installations")
    app.register_blueprint(interactions_bp, url_prefix="/api/interactions")
    app.register_blueprint(proposals_bp, url_prefix="/api/proposals")
    app.register_blueprint(frontend_bp)
    app.register_blueprint(auth_bp)

    # Health check - manter o servico Render acordado
    @app.route("/ping")
    def ping():
        totp_on = bool(app.config.get("TOTP_SECRET"))
        return f"pong | totp={'ON' if totp_on else 'OFF'}", 200

    # Exige login em todas as rotas (exceto /login e estáticos).
    app.before_request(require_login)

    with app.app_context():
        db.create_all()
        # Migracoes automaticas — adicionar colunas novas sem perder dados.
        # Usa abordagem compatível com SQLite e PostgreSQL.
        _add_column_if_missing(app, "clients", "locality", "VARCHAR(120)")
        _add_column_if_missing(app, "clients", "proposal_path", "VARCHAR(500)")
        # DESATIVADO (jun. 2026): a migração proposal_path → client_documents já
        # cumpriu o propósito. Mantida em convivência com o multi-documento,
        # gerava um ClientDocument duplicado por proposta (stored_name
        # "client_<id>.pdf"). Ver backlog ponto 1. Definição mantida abaixo,
        # apenas para referência/reversão.
        # _migrate_proposals_to_documents(app)

    return app


def _add_column_if_missing(app, table, column, col_type):
    """Adiciona uma coluna à tabela se ainda não existir (SQLite + PostgreSQL)."""
    from sqlalchemy import text, inspect
    with app.app_context():
        try:
            insp = inspect(db.engine)
            existing = [c["name"] for c in insp.get_columns(table)]
            if column not in existing:
                with db.engine.connect() as conn:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
                    conn.commit()
        except Exception:
            pass  # tabela ainda não existe ou outro erro não crítico


def _migrate_proposals_to_documents(app):
    """Migra proposal_path legado → client_documents (idempotente)."""
    with app.app_context():
        try:
            from sqlalchemy import inspect
            insp = inspect(db.engine)
            if "client_documents" not in insp.get_table_names():
                return
            from .models import Client, ClientDocument
            clients = Client.query.filter(
                Client.proposal_path.isnot(None), Client.proposal_path != ""
            ).all()
            for client in clients:
                already = ClientDocument.query.filter_by(
                    client_id=client.id, stored_name=client.proposal_path
                ).first()
                if not already:
                    doc = ClientDocument(
                        client_id=client.id,
                        original_name=client.proposal_path,
                        stored_name=client.proposal_path,
                        label="Proposta",
                    )
                    db.session.add(doc)
            db.session.commit()
        except Exception:
            db.session.rollback()
