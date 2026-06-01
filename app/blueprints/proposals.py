import os
from flask import Blueprint, render_template, make_response, current_app, url_for
from weasyprint import HTML
from .. import db
from ..models import Client

bp = Blueprint("proposals", __name__)


def _logo_file_uri():
    """Absolute file:// URI so WeasyPrint can load the logo from disk."""
    path = os.path.join(current_app.static_folder, "img", "c2s-symbol.png")
    return f"file://{path}"


@bp.get("/client/<int:client_id>/pdf")
def generate_pdf(client_id):
    client = db.get_or_404(Client, client_id)
    html_string = render_template("proposal.html", client=client, logo_uri=_logo_file_uri())
    pdf = HTML(string=html_string).write_pdf()
    response = make_response(pdf)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = (
        f'attachment; filename="proposta_{client.id}_{client.name.replace(" ", "_")}.pdf"'
    )
    return response


@bp.get("/client/<int:client_id>/preview")
def preview_proposal(client_id):
    client = db.get_or_404(Client, client_id)
    logo_uri = url_for("static", filename="img/c2s-symbol.png")
    return render_template("proposal.html", client=client, logo_uri=logo_uri)
