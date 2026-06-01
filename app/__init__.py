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

    # Exige login em todas as rotas (exceto /login e estáticos).
    app.before_request(require_login)

    with app.app_context():
        db.create_all()

    return app
