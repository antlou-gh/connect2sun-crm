from datetime import date
from flask import Blueprint, jsonify, request
from .. import db
from ..models import Client, Interaction

bp = Blueprint("interactions", __name__)

VALID_TYPES = {"call", "email", "visit", "whatsapp", "meeting", "other"}


def _parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


@bp.get("/client/<int:client_id>")
def list_interactions(client_id):
    db.get_or_404(Client, client_id)
    interactions = (
        Interaction.query.filter_by(client_id=client_id)
        .order_by(Interaction.created_at.desc())
        .all()
    )
    return jsonify([i.to_dict() for i in interactions])


@bp.post("/client/<int:client_id>")
def create_interaction(client_id):
    db.get_or_404(Client, client_id)
    body = request.get_json(silent=True) or {}

    if not body.get("interaction_type"):
        return jsonify({"error": "interaction_type is required"}), 400
    if body["interaction_type"] not in VALID_TYPES:
        return jsonify({"error": f"interaction_type must be one of: {', '.join(VALID_TYPES)}"}), 400
    if not body.get("summary"):
        return jsonify({"error": "summary is required"}), 400

    interaction = Interaction(
        client_id=client_id,
        interaction_type=body["interaction_type"],
        summary=body["summary"],
        outcome=body.get("outcome"),
        next_action=body.get("next_action"),
        next_action_date=_parse_date(body.get("next_action_date")),
    )
    db.session.add(interaction)
    db.session.commit()
    return jsonify(interaction.to_dict()), 201


@bp.put("/<int:interaction_id>")
def update_interaction(interaction_id):
    interaction = db.get_or_404(Interaction, interaction_id)
    body = request.get_json(silent=True) or {}

    if "interaction_type" in body:
        if body["interaction_type"] not in VALID_TYPES:
            return jsonify({"error": f"interaction_type must be one of: {', '.join(VALID_TYPES)}"}), 400
        interaction.interaction_type = body["interaction_type"]

    for field in ("summary", "outcome", "next_action"):
        if field in body:
            setattr(interaction, field, body[field])
    if "next_action_date" in body:
        interaction.next_action_date = _parse_date(body["next_action_date"])

    db.session.commit()
    return jsonify(interaction.to_dict())


@bp.delete("/<int:interaction_id>")
def delete_interaction(interaction_id):
    interaction = db.get_or_404(Interaction, interaction_id)
    db.session.delete(interaction)
    db.session.commit()
    return "", 204
