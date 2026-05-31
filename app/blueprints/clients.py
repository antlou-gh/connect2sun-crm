from flask import Blueprint, jsonify, request
from .. import db
from ..models import Client

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
