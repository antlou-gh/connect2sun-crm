from datetime import datetime, timezone
from . import db


class Client(db.Model):
    __tablename__ = "clients"

    id = db.Column(db.Integer, primary_key=True)
    client_number = db.Column(db.Integer, unique=True, index=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(30))
    address = db.Column(db.String(255))
    city = db.Column(db.String(80))  # concelho: Cascais, Sintra ou Outro
    locality = db.Column(db.String(120))  # localidade dentro do concelho
    postal_code = db.Column(db.String(20))
    nif = db.Column(db.String(20))
    origin = db.Column(db.String(60))  # referral, website, cold-call, fair, etc.
    proposal_status = db.Column(
        db.String(30), nullable=False, default="lead"
    )  # lead, contacted, proposal_sent, negotiation, won, lost
    notes = db.Column(db.Text)
    proposal_path = db.Column(db.String(500))  # caminho ou URL para o PDF da proposta
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    installation = db.relationship(
        "Installation", back_populates="client", uselist=False, cascade="all, delete-orphan"
    )
    interactions = db.relationship(
        "Interaction", back_populates="client", cascade="all, delete-orphan", order_by="Interaction.created_at.desc()"
    )
    documents = db.relationship(
        "ClientDocument", back_populates="client", cascade="all, delete-orphan", order_by="ClientDocument.uploaded_at.asc()"
    )

    def to_dict(self):
        return {
            "id": self.id,
            "client_number": self.client_number,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "address": self.address,
            "city": self.city,
            "locality": self.locality,
            "postal_code": self.postal_code,
            "nif": self.nif,
            "origin": self.origin,
            "proposal_status": self.proposal_status,
            "notes": self.notes,
            "proposal_path": self.proposal_path,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Installation(db.Model):
    __tablename__ = "installations"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False, unique=True)
    power_kwp = db.Column(db.Float)           # total power in kWp
    num_modules = db.Column(db.Integer)
    module_model = db.Column(db.String(120))  # e.g. "Jinko 415W"
    inverter_model = db.Column(db.String(120))
    inverter_power_kw = db.Column(db.Float)
    battery_model = db.Column(db.String(120))
    battery_capacity_kwh = db.Column(db.Float)
    installation_date = db.Column(db.Date)
    roof_type = db.Column(db.String(60))       # tiles, flat, ground
    orientation = db.Column(db.String(30))     # south, east-west, etc.
    tilt_degrees = db.Column(db.Float)
    estimated_annual_kwh = db.Column(db.Float)
    total_price = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    client = db.relationship("Client", back_populates="installation")

    def to_dict(self):
        return {
            "id": self.id,
            "client_id": self.client_id,
            "power_kwp": self.power_kwp,
            "num_modules": self.num_modules,
            "module_model": self.module_model,
            "inverter_model": self.inverter_model,
            "inverter_power_kw": self.inverter_power_kw,
            "battery_model": self.battery_model,
            "battery_capacity_kwh": self.battery_capacity_kwh,
            "installation_date": self.installation_date.isoformat() if self.installation_date else None,
            "roof_type": self.roof_type,
            "orientation": self.orientation,
            "tilt_degrees": self.tilt_degrees,
            "estimated_annual_kwh": self.estimated_annual_kwh,
            "total_price": self.total_price,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Interaction(db.Model):
    __tablename__ = "interactions"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False)
    interaction_type = db.Column(db.String(40), nullable=False)  # call, email, visit, whatsapp, meeting
    summary = db.Column(db.Text, nullable=False)
    outcome = db.Column(db.String(120))
    next_action = db.Column(db.String(255))
    next_action_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    client = db.relationship("Client", back_populates="interactions")

    def to_dict(self):
        return {
            "id": self.id,
            "client_id": self.client_id,
            "interaction_type": self.interaction_type,
            "summary": self.summary,
            "outcome": self.outcome,
            "next_action": self.next_action,
            "next_action_date": self.next_action_date.isoformat() if self.next_action_date else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ClientDocument(db.Model):
    __tablename__ = "client_documents"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False)
    original_name = db.Column(db.String(255), nullable=False)   # nome original do ficheiro
    stored_name = db.Column(db.String(255), nullable=False)     # nome guardado em disco
    label = db.Column(db.String(120))                           # descrição opcional
    uploaded_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    client = db.relationship("Client", back_populates="documents")

    def to_dict(self):
        return {
            "id": self.id,
            "client_id": self.client_id,
            "original_name": self.original_name,
            "label": self.label,
            "uploaded_at": self.uploaded_at.isoformat() if self.uploaded_at else None,
        }
