# Connect2Sun CRM

CRM interno para gestão de clientes e propostas de instalações de energia solar.

## Requisitos

- Python 3.10+
- pip

> No Ubuntu/Debian, o WeasyPrint requer algumas bibliotecas de sistema:
> ```bash
> sudo apt install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b
> ```

## Instalação

```bash
# 1. Clonar o repositório
git clone <url-do-repo>
cd connect2sun-crm

# 2. Criar e ativar o ambiente virtual
python3 -m venv venv
source venv/bin/activate        # Linux/macOS
# venv\Scripts\activate         # Windows

# 3. Instalar dependências
pip install -r requirements.txt
```

## Arrancar o servidor

```bash
python run.py
```

A aplicação fica disponível em **http://127.0.0.1:5000**.

A base de dados SQLite (`connect2sun.db`) é criada automaticamente na primeira execução.

## Estrutura

```
connect2sun-crm/
├── app/
│   ├── __init__.py          # app factory
│   ├── models.py            # Client, Installation, Interaction
│   ├── blueprints/
│   │   ├── clients.py       # /api/clients/
│   │   ├── installations.py # /api/installations/
│   │   ├── interactions.py  # /api/interactions/
│   │   ├── proposals.py     # /api/proposals/ (PDF)
│   │   └── frontend.py      # serve a SPA
│   └── templates/
│       ├── index.html       # SPA (dashboard + clientes)
│       └── proposal.html    # template da proposta PDF
├── config.py
├── requirements.txt
└── run.py
```

## API REST

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/api/clients/` | Listar clientes (filtro `?status=`) |
| `POST` | `/api/clients/` | Criar cliente |
| `GET` | `/api/clients/<id>` | Detalhe + instalação + interações |
| `PUT` | `/api/clients/<id>` | Atualizar cliente |
| `DELETE` | `/api/clients/<id>` | Apagar cliente |
| `GET/POST/PUT/DELETE` | `/api/installations/client/<id>` | Dados técnicos |
| `GET/POST` | `/api/interactions/client/<id>` | Histórico de interações |
| `PUT/DELETE` | `/api/interactions/<id>` | Editar/apagar interação |
| `GET` | `/api/proposals/client/<id>/pdf` | Download da proposta em PDF |
| `GET` | `/api/proposals/client/<id>/preview` | Pré-visualização HTML da proposta |

## API de máquina (`/api/v1` — MCP)

API para consumo por máquina (futuro servidor MCP). **Não usa a sessão de
browser**: é autenticada por uma **chave estática** enviada no header
`X-API-Key`, validada contra a env var `MCP_API_KEY`. Se `MCP_API_KEY` não
estiver definida, a `/api/v1` fica **fechada** (fail-closed) e devolve `401`.

Privilégio mínimo: só **criar** movimentos e **ler** (clientes + transações).
Não há `PUT`/`DELETE` — a máquina nunca altera nem apaga.

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `POST` | `/api/v1/transacoes` | Criar movimento (mesma validação do endpoint humano; `entidade_emissora` é obrigatória) |
| `GET` | `/api/v1/clientes` | Listar clientes; `?nif=<nif>` filtra por NIF exato |
| `GET` | `/api/v1/transacoes` | Consultar movimentos (`?ano&mes&tipo_movimento&categoria&estado&cliente_id&q`) |

Gera a chave com:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Exemplos de `curl` (assumindo `X-API-Key: $MCP_API_KEY`):

```bash
# Criar um movimento (entidade_emissora é obrigatória; num_factura é opcional
# mas incentivado sempre que exista documento associado)
curl -X POST http://localhost:5000/api/v1/transacoes \
  -H "X-API-Key: $MCP_API_KEY" -H "Content-Type: application/json" \
  -d '{"descricao": "Fatura FT 2026/1", "valor": 1230.0, "data": "2026-06-30",
       "tipo_movimento": "Facturação", "estado": "Fechado",
       "entidade_emissora": "C2S", "num_factura": "FT 2026/1"}'

# Resolver NIF → cliente
curl -H "X-API-Key: $MCP_API_KEY" "http://localhost:5000/api/v1/clientes?nif=500123456"

# Consultar movimentos de 2026
curl -H "X-API-Key: $MCP_API_KEY" "http://localhost:5000/api/v1/transacoes?ano=2026"
```

## Variáveis de ambiente

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `SECRET_KEY` | `dev-secret-connect2sun` | Chave secreta Flask |
| `DATABASE_URL` | `sqlite:///connect2sun.db` | URI da base de dados |
| `MCP_API_KEY` | _(vazio)_ | Chave da API de máquina `/api/v1` (`X-API-Key`). Vazia → `/api/v1` fechada |

Cria um ficheiro `.env` na raiz para substituir os valores padrão:

```env
SECRET_KEY=uma-chave-secreta-forte
DATABASE_URL=sqlite:///connect2sun.db
```
