import hmac
import io
import base64

from flask import (
    Blueprint, request, session, redirect, url_for,
    render_template, current_app, jsonify,
)

bp = Blueprint("auth", __name__)


def _home_endpoint(role):
    """Rota de destino após login, consoante o perfil."""
    return "frontend.financeiro" if role == "contabilista" else "frontend.index"


def _totp_secret_for(role):
    key = "CONTAB_TOTP_SECRET" if role == "contabilista" else "TOTP_SECRET"
    return current_app.config.get(key)


# ── Login (passo 1 — password) ────────────────────────────────────────────────

@bp.get("/login")
def login_page():
    if session.get("authed"):
        return redirect(url_for(_home_endpoint(session.get("role"))))
    return render_template("login.html", error=None)


@bp.post("/login")
def login():
    password = request.form.get("password") or ""
    app_password = current_app.config.get("APP_PASSWORD") or ""
    contab_password = current_app.config.get("CONTAB_PASSWORD") or ""
    # Avalia sempre as duas comparações antes de decidir — evita um
    # short-circuit que revelasse por timing qual das duas passwords
    # (se alguma) estava a ser testada primeiro.
    match_admin = bool(app_password) and hmac.compare_digest(password, app_password)
    match_contab = bool(contab_password) and hmac.compare_digest(password, contab_password)

    if match_admin:
        role = "admin"
    elif match_contab:
        role = "contabilista"
    else:
        return render_template("login.html", error="Palavra-passe incorreta."), 401

    totp_secret = _totp_secret_for(role)
    if totp_secret:
        # Password OK mas ainda falta o segundo fator.
        session["pw_role"] = role
        session["pw_verified"] = True
        session.permanent = True
        return redirect(url_for("auth.mfa_page"))

    if role == "contabilista":
        # MFA obrigatório para a contabilista, sem fallback — o atalho de
        # login direto sem MFA só existe para o admin em modo dev local.
        return render_template(
            "login.html",
            error="Acesso da contabilista requer MFA configurado. Contacta o administrador.",
        ), 401

    # MFA não configurado — login direto (modo dev / local, admin apenas).
    session["role"] = "admin"
    session["authed"] = True
    session.permanent = True
    return redirect(url_for("frontend.index"))


# ── MFA (passo 2 — TOTP) ──────────────────────────────────────────────────────

@bp.get("/mfa")
def mfa_page():
    if session.get("authed"):
        return redirect(url_for(_home_endpoint(session.get("role"))))
    if not session.get("pw_verified"):
        return redirect(url_for("auth.login_page"))
    return render_template("mfa.html", error=None)


@bp.post("/mfa")
def mfa_verify():
    if not session.get("pw_verified"):
        return redirect(url_for("auth.login_page"))
    role = session.get("pw_role")
    code = (request.form.get("code") or "").strip().replace(" ", "")
    totp_secret = _totp_secret_for(role)
    if not totp_secret:
        session.clear()
        return redirect(url_for("auth.login_page"))

    import pyotp
    totp = pyotp.TOTP(totp_secret)
    # valid_window=1 tolera ±30 s de drift do relógio.
    if totp.verify(code, valid_window=1):
        session.pop("pw_verified", None)
        session.pop("pw_role", None)
        session["role"] = role
        session["authed"] = True
        return redirect(url_for(_home_endpoint(role)))

    return render_template("mfa.html", error="Código inválido. Tenta novamente."), 401


# ── Setup MFA (só acessível com sessão autenticada) ───────────────────────────

@bp.get("/mfa/setup")
def mfa_setup():
    """Mostra QR code para configurar o autenticador. Requer login."""
    if not session.get("authed") and not session.get("pw_verified"):
        return redirect(url_for("auth.login_page"))

    role = session.get("role") or session.get("pw_role") or "admin"
    totp_secret = _totp_secret_for(role)
    var_name = "CONTAB_TOTP_SECRET" if role == "contabilista" else "TOTP_SECRET"
    if not totp_secret:
        return render_template(
            "mfa_setup.html",
            qr_data=None, secret=None, var_name=var_name,
            error=f"{var_name} não está definido nas variáveis de ambiente.",
        )

    import pyotp, qrcode
    totp = pyotp.TOTP(totp_secret)
    account_name = "contabilista" if role == "contabilista" else "connect2sun-crm"
    uri = totp.provisioning_uri(name=account_name, issuer_name="Connect2Sun CRM")

    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    return render_template(
        "mfa_setup.html", qr_data=qr_b64, secret=totp_secret, var_name=var_name, error=None
    )


# ── Logout ────────────────────────────────────────────────────────────────────

@bp.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login_page"))


# ── Middleware (before_request) ───────────────────────────────────────────────

# Endpoints acessíveis à contabilista sem restrição de método (só GET de qq forma).
_CONTAB_PUBLIC_ENDPOINTS = ("frontend.financeiro", "auth.logout", "static", "ping")
# Endpoints do financeiro acessíveis à contabilista — só em GET, mesmo que o
# mesmo path sirva outros métodos (ex.: POST /api/financeiro/transacoes).
_CONTAB_FINANCEIRO_GET_ENDPOINTS = (
    "financeiro.list_transacoes",
    "financeiro.meta",
    "financeiro.exportar",
)


def require_login():
    """Bloqueia tudo exceto rotas de autenticação e ficheiros estáticos.

    Sessões `role == "admin"` (ou sessões antigas sem `role`, criadas antes
    desta feature) têm acesso total. `role == "contabilista"` fica limitada a
    uma whitelist server-side — a barreira real é aqui, não no frontend.
    """
    # API de máquina (/api/v1): governada SÓ pela chave, nunca pela sessão de
    # browser. Verificação exaustiva e prioritária — se o path é /api/v1/ mas a
    # chave falha, devolve 401 aqui e NÃO cai na lógica de sessão humana.
    if request.path.startswith("/api/v1/"):
        from ..api_auth import verificar_api_key
        if verificar_api_key(request):
            return None
        return jsonify({"error": "API key inválida ou em falta"}), 401

    if not session.get("authed"):
        public = ("auth.login", "auth.login_page", "auth.mfa_page",
                  "auth.mfa_verify", "auth.mfa_setup", "ping", "static")
        if request.endpoint in public:
            return None
        if request.path.startswith("/api/"):
            return jsonify({"error": "Não autenticado"}), 401
        return redirect(url_for("auth.login_page"))

    role = session.get("role")
    if role is None or role == "admin":
        return None  # acesso total (admin, ou sessão antiga sem `role`)

    if role == "contabilista":
        if request.endpoint in _CONTAB_PUBLIC_ENDPOINTS:
            return None
        if request.method == "GET" and request.endpoint in _CONTAB_FINANCEIRO_GET_ENDPOINTS:
            return None
        if request.path.startswith("/api/"):
            return jsonify({"error": "Sem permissão"}), 403
        return redirect(url_for("frontend.financeiro"))

    # `role` desconhecido/corrompido — falha fechado.
    session.clear()
    return redirect(url_for("auth.login_page"))
