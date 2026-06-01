# Deploy em produção — Render.com (grátis)

A app fica disponível num domínio público HTTPS (`https://<nome>.onrender.com`),
acessível por computador **e telemóvel**.

## Pré-requisitos
- Conta gratuita em https://render.com (podes entrar com o GitHub).
- O código tem de estar num repositório Git remoto (GitHub/GitLab). Já tens git
  local; falta enviar para o GitHub.

## 1. Enviar o código para o GitHub
```bash
# cria o repositório no github.com (ex.: connect2sun-crm) e depois:
git add .
git commit -m "App pronta para produção (Docker + Render)"
git branch -M main
git remote add origin https://github.com/<o-teu-utilizador>/connect2sun-crm.git
git push -u origin main
```

## 2. Criar a base de dados Postgres grátis (Neon)
A app está configurada para guardar os dados num **Postgres** — assim ficam
**permanentes** (não se perdem em reinícios/deploys). O tier gratuito do Neon
é permanente e suficiente para um CRM.

1. Cria conta grátis em https://neon.tech (entra com o GitHub).
2. **Create project** (escolhe a região mais próxima, ex.: Frankfurt/EU).
3. No painel do projeto, em **Connection string**, copia a string no formato:
   `postgresql://utilizador:password@ep-xxxx.eu-central-1.aws.neon.tech/neondb?sslmode=require`
4. Guarda essa string — vais colá-la no Render no passo seguinte.

> Em alternativa ao Neon, o Supabase (https://supabase.com) também serve: usa
> **Project Settings → Database → Connection string (URI)**.

## 3. Criar o serviço no Render
1. No dashboard do Render: **New → Blueprint**.
2. Escolhe o repositório `connect2sun-crm`. O Render lê o `render.yaml` e cria
   o serviço web (runtime Docker, plano free, HTTPS).
3. Vai pedir o valor da variável **`DATABASE_URL`** → cola aqui a connection
   string do Neon do passo 2.
4. Confirma e faz **Apply**. O primeiro build demora ~3–5 min (instala WeasyPrint).
   As tabelas são criadas automaticamente no Neon no primeiro arranque.
5. No fim ficas com o URL público, ex.: `https://connect2sun-crm.onrender.com`.

> Alternativa sem blueprint: **New → Web Service** → liga o repo → Runtime
> **Docker** → Plan **Free** → em **Environment** adiciona `DATABASE_URL` com a
> string do Neon. O `Dockerfile` trata do resto.

## 3. Abrir no telemóvel
Abre o URL `.onrender.com` no browser do telemóvel. A interface já é responsiva.
Podes "Adicionar ao ecrã principal" para ficar como atalho/app.

## ⚠️ Notas do plano free
- Os **dados estão seguros** no Postgres do Neon (persistentes entre deploys).
- O **serviço web** free do Render **adormece** após ~15 min sem tráfego; o
  primeiro acesso seguinte demora alguns segundos a acordar. Os dados não se
  perdem — só o contentor é que reinicia.

## Variáveis de ambiente
| Variável | Para quê |
|----------|----------|
| `SECRET_KEY` | gerada automaticamente pelo `render.yaml` |
| `DATABASE_URL` | connection string do Neon (Postgres) — obrigatória em produção |
| `PORT` | fornecida pelo Render; o Dockerfile já a usa |

O `config.py` aceita `postgres://`, `postgresql://` ou
`postgresql+psycopg://` e normaliza para o driver psycopg3 automaticamente.

## Migração dos dados locais para produção
A BD do Neon começa vazia (as tabelas são criadas no primeiro arranque). Para
levar os clientes que já tens localmente:
1. Localmente, em **Clientes → Exportar CSV**.
2. No site em produção (`.onrender.com`), em **Clientes → Importar CSV**.
O nº de cliente e o concelho vão no CSV e são preservados/normalizados.

## Testar localmente com Postgres (opcional)
```bash
export DATABASE_URL="postgresql://utilizador:password@host/neondb?sslmode=require"
python run.py    # ou: gunicorn run:app
```
