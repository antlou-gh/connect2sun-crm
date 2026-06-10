import hmac
import io
import base64

from flask import (
    Blueprint, request, session, redirect, url_for,
    render_template, current_app, jsonify,
)

bp = Blueprint("auth", __name__)


# ── Login (passo 1 — password) ────────────────────────────────────────────────

@bp.get("/login")
def login_page():
    if session.get("authed"):
        return redirect(url_for("frontend.index"))
    return render_template("login.html", error=None)


@bp.post("/login")
def login():
    password = request.form.get("password") or ""
    expected = current_app.config["APP_PASSWORD"]
    if expected and hmac.compare_digest(password, expected):
        totp_secret = current_app.config.get("TOTP_SECRET")
        if totp_secret:
            # Password OK mas ainda falta o segundo fator.
            session["pw_verified"] = True
            session.permanent = True
            return redirect(url_for("auth.mfa_page"))
        # MFA não configurado — login direto (modo dev / local).
        session["authed"] = True
        session.permanent = True
        return redirect(url_for("frontend.index"))
    return render_template("login.html", error="Palavra-passe incorreta."), 401


# ── MFA (passo 2 — TOTP) ──────────────────────────────────────────────────────

@bp.get("/mfa")
def mfa_page():
    if session.get("authed"):
        return redirect(url_for("frontend.index"))
    if not session.get("pw_verified"):
        return redirect(url_for("auth.login_page"))
    return render_template("mfa.html", error=None)


@bp.post("/mfa")
def mfa_verify():
    if not session.get("pw_verified"):
        return redirect(url_for("auth.login_page"))
    code = (request.form.get("code") or "").strip().replace(" ", "")
    totp_secret = current_app.config.get("TOTP_SECRET")
    if not totp_secret:
        session.clear()
        return redirect(url_for("auth.login_page"))

    import pyotp
    totp = pyotp.TOTP(totp_secret)
    # valid_window=1 tolera ±30 s de drift do relógio.
    if totp.verify(code, valid_window=1):
        session.pop("pw_verified", None)
        session["authed"] = True
        return redirect(url_for("frontend.index"))

    return render_template("mfa.html", error="Código inválido. Tenta novamente."), 401


# ── Setup MFA (só acessível com sessão autenticada) ───────────────────────────

@bp.get("/mfa/setup")
def mfa_setup():
    """Mostra QR code para configurar o autenticador. Requer login."""
    if not session.get("authed") and not session.get("pw_verified"):
        return redirect(url_for("auth.login_page"))

    totp_secret = current_app.config.get("TOTP_SECRET")
    if not totp_secret:
        return render_template(
            "mfa_setup.html",
            qr_data=None, secret=None,
            error="TOTP_SECRET não está definido nas variáveis de ambiente.",
        )

    import pyotp, qrcode
    totp = pyotp.TOTP(totp_secret)
    uri = totp.provisioning_uri(name="connect2sun-crm", issuer_name="Connect2Sun CRM")

    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    return render_template("mfa_setup.html", qr_data=qr_b64, secret=totp_secret, error=None)


# ── Logout ────────────────────────────────────────────────────────────────────

@bp.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login_page"))


# ── Middleware (before_request) ───────────────────────────────────────────────

def require_login():
    """Bloqueia tudo exceto rotas de autenticação e ficheiros estáticos."""
    if session.get("authed"):
        return None
    public = ("auth.login", "auth.login_page", "auth.mfa_page",
              "auth.mfa_verify", "auth.mfa_setup", "static")
    if request.endpoint in public:
        return None
    if request.path.startswith("/api/"):
        return jsonify({"error": "Não autenticado"}), 401
    return redirect(url_for("auth.login_page"))
