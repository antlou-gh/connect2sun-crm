import hmac
from flask import (
    Blueprint, request, session, redirect, url_for, render_template,
    current_app, jsonify,
)

bp = Blueprint("auth", __name__)


@bp.get("/login")
def login_page():
    if session.get("authed"):
        return redirect(url_for("frontend.index"))
    return render_template("login.html", error=None)


@bp.post("/login")
def login():
    password = request.form.get("password") or ""
    expected = current_app.config["APP_PASSWORD"]
    # compare_digest evita timing attacks na comparação da password.
    if expected and hmac.compare_digest(password, expected):
        session["authed"] = True
        session.permanent = True
        return redirect(url_for("frontend.index"))
    return render_template("login.html", error="Palavra-passe incorreta."), 401


@bp.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login_page"))


def require_login():
    """before_request global: bloqueia tudo exceto login e ficheiros estáticos."""
    if session.get("authed"):
        return None
    if request.endpoint in ("auth.login", "auth.login_page", "static"):
        return None
    # Pedidos à API recebem 401 (o frontend trata e redireciona para /login).
    if request.path.startswith("/api/"):
        return jsonify({"error": "Não autenticado"}), 401
    return redirect(url_for("auth.login_page"))
