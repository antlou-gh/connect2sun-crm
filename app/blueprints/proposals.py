from flask import Blueprint, render_template, make_response
from weasyprint import HTML
from .. import db
from ..models import Client

bp = Blueprint("proposals", __name__)


@bp.get("/client/<int:client_id>/pdf")
def generate_pdf(client_id):
    client = db.get_or_404(Client, client_id)
    html_string = render_template("proposal.html", client=client)
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
    return render_template("proposal.html", client=client)
