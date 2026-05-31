import csv
import io
from flask import Blueprint, jsonify, request, make_response
from .. import db
from ..models import Client

CSV_FIELDS = ("name", "email", "phone", "address", "city", "postal_code",
              "nif", "origin", "proposal_status", "notes")

bp = Blueprint("clients", __name__)


@bp.get("/")
def list_clients():
    status = request.args.get("status")
    query = Client.query
    if status:
        query = query.filter_by(proposal_status=status)
    clients = query.order_by(Client.created_at.desc()).all()
    return jsonify([c.to_dict() for c in clients])


@bp.get("/<int:client_id>")
def get_client(client_id):
    client = db.get_or_404(Client, client_id)
    data = client.to_dict()
    data["installation"] = client.installation.to_dict() if client.installation else None
    data["interactions"] = [i.to_dict() for i in client.interactions]
    return jsonify(data)


@bp.post("/")
def create_client():
    body = request.get_json(silent=True) or {}
    required = ("name", "email")
    missing = [f for f in required if not body.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    if Client.query.filter_by(email=body["email"]).first():
        return jsonify({"error": "Email already registered"}), 409

    client = Client(
        name=body["name"],
        email=body["email"],
        phone=body.get("phone"),
        address=body.get("address"),
        city=body.get("city"),
        postal_code=body.get("postal_code"),
        nif=body.get("nif"),
        origin=body.get("origin"),
        proposal_status=body.get("proposal_status", "lead"),
        notes=body.get("notes"),
    )
    db.session.add(client)
    db.session.commit()
    return jsonify(client.to_dict()), 201


@bp.put("/<int:client_id>")
def update_client(client_id):
    client = db.get_or_404(Client, client_id)
    body = request.get_json(silent=True) or {}

    if "email" in body and body["email"] != client.email:
        if Client.query.filter_by(email=body["email"]).first():
            return jsonify({"error": "Email already registered"}), 409

    fields = ("name", "email", "phone", "address", "city", "postal_code", "nif",
              "origin", "proposal_status", "notes")
    for field in fields:
        if field in body:
            setattr(client, field, body[field])

    db.session.commit()
    return jsonify(client.to_dict())


@bp.delete("/<int:client_id>")
def delete_client(client_id):
    client = db.get_or_404(Client, client_id)
    db.session.delete(client)
    db.session.commit()
    return "", 204


@bp.get("/export.csv")
def export_csv():
    clients = Client.query.order_by(Client.created_at).all()
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for c in clients:
        writer.writerow({f: getattr(c, f) or "" for f in CSV_FIELDS})
    response = make_response(buf.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = "attachment; filename=clientes_connect2sun.csv"
    return response


@bp.post("/import")
def import_csv():
    file = request.files.get("file")
    if not file or not file.filename.endswith(".csv"):
        return jsonify({"error": "Ficheiro CSV obrigatório"}), 400

    text = file.stream.read().decode("utf-8-sig")  # strip BOM if present
    reader = csv.DictReader(io.StringIO(text))

    created = updated = skipped = 0
    errors = []

    for i, row in enumerate(reader, start=2):
        name = (row.get("name") or "").strip()
        email = (row.get("email") or "").strip().lower()
        if not name or not email:
            errors.append(f"Linha {i}: name e email são obrigatórios")
            skipped += 1
            continue

        existing = Client.query.filter_by(email=email).first()
        if existing:
            for field in CSV_FIELDS:
                val = (row.get(field) or "").strip()
                if val:
                    setattr(existing, field, val)
            updated += 1
        else:
            client = Client(**{
                f: (row.get(f) or "").strip() or None for f in CSV_FIELDS
            })
            client.proposal_status = client.proposal_status or "lead"
            db.session.add(client)
            created += 1

    db.session.commit()
    return jsonify({"created": created, "updated": updated, "skipped": skipped, "errors": errors})
