from datetime import date
from flask import Blueprint, jsonify, request
from .. import db
from ..models import Client, Installation

bp = Blueprint("installations", __name__)


def _parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


@bp.get("/client/<int:client_id>")
def get_installation(client_id):
    db.get_or_404(Client, client_id)
    inst = Installation.query.filter_by(client_id=client_id).first_or_404()
    return jsonify(inst.to_dict())


@bp.post("/client/<int:client_id>")
def create_installation(client_id):
    client = db.get_or_404(Client, client_id)
    if client.installation:
        return jsonify({"error": "Installation already exists; use PUT to update"}), 409

    body = request.get_json(silent=True) or {}
    inst = Installation(
        client_id=client_id,
        power_kwp=body.get("power_kwp"),
        num_modules=body.get("num_modules"),
        module_model=body.get("module_model"),
        inverter_model=body.get("inverter_model"),
        inverter_power_kw=body.get("inverter_power_kw"),
        battery_model=body.get("battery_model"),
        battery_capacity_kwh=body.get("battery_capacity_kwh"),
        installation_date=_parse_date(body.get("installation_date")),
        roof_type=body.get("roof_type"),
        orientation=body.get("orientation"),
        tilt_degrees=body.get("tilt_degrees"),
        estimated_annual_kwh=body.get("estimated_annual_kwh"),
        total_price=body.get("total_price"),
    )
    db.session.add(inst)
    db.session.commit()
    return jsonify(inst.to_dict()), 201


@bp.put("/client/<int:client_id>")
def update_installation(client_id):
    db.get_or_404(Client, client_id)
    inst = Installation.query.filter_by(client_id=client_id).first_or_404()
    body = request.get_json(silent=True) or {}

    fields = ("power_kwp", "num_modules", "module_model", "inverter_model",
              "inverter_power_kw", "battery_model", "battery_capacity_kwh",
              "roof_type", "orientation", "tilt_degrees", "estimated_annual_kwh",
              "total_price")
    for field in fields:
        if field in body:
            setattr(inst, field, body[field])
    if "installation_date" in body:
        inst.installation_date = _parse_date(body["installation_date"])

    db.session.commit()
    return jsonify(inst.to_dict())


@bp.delete("/client/<int:client_id>")
def delete_installation(client_id):
    db.get_or_404(Client, client_id)
    inst = Installation.query.filter_by(client_id=client_id).first_or_404()
    db.session.delete(inst)
    db.session.commit()
    return "", 204
