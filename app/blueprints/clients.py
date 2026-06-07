import csv
import io
from flask import Blueprint, jsonify, request, make_response
from .. import db
from ..models import Client

CSV_FIELDS = ("client_number", "name", "email", "phone", "address", "city",
              "locality", "postal_code", "nif", "origin", "proposal_status", "notes")

# Concelhos suportados; qualquer outro valor é qualificado como "Outro".
CONCELHOS = ("Cascais", "Sintra")


def normalize_concelho(value):
    if not value:
        return None
    value = value.strip()
    for c in CONCELHOS:
        if value.lower() == c.lower():
            return c
    return "Outro"


def next_client_number():
    """Maior nº de cliente existente + 1 (1 se ainda não houver clientes)."""
    current = db.session.query(db.func.max(Client.client_number)).scalar()
    return (current or 0) + 1


bp = Blueprint("clients", __name__)


@bp.get("/next-number")
def get_next_number():
    return jsonify({"next": next_client_number()})


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

    # Nº de cliente: usa o indicado, senão incrementa a partir do maior existente.
    raw_number = body.get("client_number")
    if raw_number in (None, ""):
        client_number = next_client_number()
    else:
        try:
            client_number = int(raw_number)
        except (TypeError, ValueError):
            return jsonify({"error": "Nº de cliente inválido"}), 400
        if Client.query.filter_by(client_number=client_number).first():
            return jsonify({"error": f"Nº de cliente {client_number} já existe"}), 409

    client = Client(
        client_number=client_number,
        name=body["name"],
        email=body["email"],
        phone=body.get("phone"),
        address=body.get("address"),
        city=normalize_concelho(body.get("city")),
        locality=body.get("locality"),
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

    if "client_number" in body and body["client_number"] not in (None, ""):
        try:
            new_number = int(body["client_number"])
        except (TypeError, ValueError):
            return jsonify({"error": "Nº de cliente inválido"}), 400
        if new_number != client.client_number and \
                Client.query.filter_by(client_number=new_number).first():
            return jsonify({"error": f"Nº de cliente {new_number} já existe"}), 409
        client.client_number = new_number

    fields = ("name", "email", "phone", "address", "locality", "postal_code", "nif",
              "origin", "proposal_status", "notes")
    for field in fields:
        if field in body:
            setattr(client, field, body[field])
    if "city" in body:
        client.city = normalize_concelho(body["city"])

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

    # Tenta UTF-8, depois Latin-1 (ficheiros exportados pelo Excel em PT)
    raw = file.stream.read()
    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            text = raw.decode(enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    else:
        return jsonify({"error": "Não foi possível ler o ficheiro — codificação desconhecida"}), 400

    # Normalizar line endings (
 ou  -> 
) para evitar problemas com StringIO
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Detectar separador automaticamente (vírgula ou ponto-e-vírgula)
    first_line = text.split("\n")[0] if text else ""
    delimiter = ";" if first_line.count(";") > first_line.count(",") else ","

    try:
        # Usar splitlines() em vez de StringIO para garantir parsing correcto
        lines = [l for l in text.splitlines() if l.strip()]
        reader = csv.DictReader(lines, delimiter=delimiter)
        rows = list(reader)
    except Exception as e:
        return jsonify({"error": f"Erro ao interpretar CSV: {str(e)}"}), 400

    if not rows:
        return jsonify({"error": "Ficheiro CSV vazio ou sem dados"}), 400

    # Debug: incluir os nomes das colunas detectadas na resposta
    detected_fields = list(rows[0].keys()) if rows else []
    first_row_sample = dict(rows[0]) if rows else {}
    first_line_raw = text.split("\n")[0][:200]  # primeiros 200 chars da 1a linha

    created = updated = skipped = 0
    errors = []

    for i, row in enumerate(rows, start=2):
        try:
            name = (row.get("name") or "").strip()
            email = (row.get("email") or "").strip().lower()
            # Limpar caracteres inválidos do email
            email = email.replace(">", "").replace("<", "").strip()
            if not name or not email:
                errors.append(f"Linha {i}: name e email são obrigatórios")
                skipped += 1
                continue

            existing = Client.query.filter_by(email=email).first()
            if existing:
                for field in CSV_FIELDS:
                    val = (row.get(field) or "").strip()
                    if not val:
                        continue
                    if field == "client_number":
                        continue
                    if field == "city":
                        val = normalize_concelho(val)
                    setattr(existing, field, val)
                updated += 1
            else:
                data = {f: (row.get(f) or "").strip() or None
                        for f in CSV_FIELDS if f not in ("client_number", "city")}
                data["email"] = email  # usa o email já limpo
                client = Client(**data)
                client.city = normalize_concelho(row.get("city"))
                client.proposal_status = client.proposal_status or "lead"
                num = (row.get("client_number") or "").strip()
                try:
                    client.client_number = int(num) if num else next_client_number()
                except ValueError:
                    client.client_number = next_client_number()
                db.session.add(client)
                db.session.flush()
                created += 1
        except Exception as e:
            errors.append(f"Linha {i}: erro inesperado — {str(e)}")
            skipped += 1
            db.session.rollback()
            continue

    db.session.commit()
    return jsonify({"created": created, "updated": updated, "skipped": skipped, "errors": errors, "detected_fields": detected_fields, "first_line_raw": first_line_raw, "first_row_sample": first_row_sample, "delimiter_used": delimiter})
