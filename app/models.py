from datetime import datetime, timezone
from . import db


# ── Valores fechados do módulo financeiro ─────────────────────────────────────
# Usamos String + listas de constantes validadas na aplicação (NÃO ENUM nativo
# do Postgres: acrescentar valores a um enum mais tarde é doloroso).
ESTADOS = ["Fechado", "Falta receber", "Falta pagar", "Pag. Parcial"]
TIPOS_MOVIMENTO = ["Custos gerais", "Facturação", "Material/Serviços",
                   "Nota de crédito", "Pagamentos ao Estado"]
CATEGORIAS = ["Estrutura", "Viaturas", "Marketing", "Seguros", "Royalties"]

# Meses em português — usado pela importação (texto→nº) e pela exportação (nº→texto)
MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
         "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]


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
    # DESCONTINUADO (jun. 2026): substituído por ClientDocument. Coluna mantida
    # vazia para evitar migração destrutiva de schema; já não é lida nem escrita.
    proposal_path = db.Column(db.String(500))
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
    # ORM apenas (não altera colunas do Client) — facilita a margem por cliente.
    # Sem cascade: apagar um cliente não deve apagar os movimentos financeiros;
    # a FK fica a NULL (movimento passa a "sem cliente").
    transacoes = db.relationship(
        "Transacao", back_populates="cliente", order_by="Transacao.data.asc()"
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


class Transacao(db.Model):
    """Movimento financeiro — fonte de verdade (substitui o Excel BD Finanças).

    Valores fechados (`estado`, `tipo_movimento`, `categoria`) são String
    validados na aplicação contra ESTADOS / TIPOS_MOVIMENTO / CATEGORIAS.
    """
    __tablename__ = "transacoes"

    id = db.Column(db.Integer, primary_key=True)
    numero_ordem = db.Column(db.Integer, unique=True, index=True)  # "Nº de ordem" do Excel
    descricao = db.Column(db.Text, nullable=False)
    valor = db.Column(db.Float, nullable=False)          # com sinal: -custo / +receita
    entidade_emissora = db.Column(db.String(120))
    num_factura = db.Column(db.String(60))
    valor_siva = db.Column(db.Float)                     # valor sem IVA
    iva = db.Column(db.Float)                            # montante de IVA
    iva_pct = db.Column(db.Float)                        # ex.: 0.23
    data = db.Column(db.Date, nullable=False, index=True)  # consolida Dia + Mês + ano
    estado = db.Column(db.String(20))                    # ESTADOS
    tipo_movimento = db.Column(db.String(30))            # TIPOS_MOVIMENTO
    categoria = db.Column(db.String(20))                 # CATEGORIAS ou NULL
    cliente_id = db.Column(
        db.Integer, db.ForeignKey("clients.id"), nullable=True, index=True
    )  # NULL = movimento sem cliente (custo geral)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    cliente = db.relationship("Client", back_populates="transacoes")

    def to_dict(self):
        return {
            "id": self.id,
            "numero_ordem": self.numero_ordem,
            "descricao": self.descricao,
            "valor": self.valor,
            "entidade_emissora": self.entidade_emissora,
            "num_factura": self.num_factura,
            "valor_siva": self.valor_siva,
            "iva": self.iva,
            "iva_pct": self.iva_pct,
            "data": self.data.isoformat() if self.data else None,
            "estado": self.estado,
            "tipo_movimento": self.tipo_movimento,
            "categoria": self.categoria,
            "cliente_id": self.cliente_id,
            "cliente_nome": self.cliente.name if self.cliente else None,
            "cliente_numero": self.cliente.client_number if self.cliente else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
