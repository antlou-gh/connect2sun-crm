from flask import Blueprint, render_template

bp = Blueprint("frontend", __name__)


@bp.get("/")
def index():
    # A contabilista nunca chega aqui: require_login (auth.py) já a
    # redireciona para frontend.financeiro antes de despachar esta view.
    return render_template("index.html")


@bp.get("/financeiro")
def financeiro():
    """Página restrita da contabilista: listagem financeira + export, só leitura."""
    return render_template("financeiro_contab.html")
