FROM python:3.12-slim

# Bibliotecas de sistema necessárias ao WeasyPrint (geração de PDF) + fontes.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz0b \
        libffi8 \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=10000

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 10000

# Render fornece $PORT; usamos shell-form para o expandir.
# 1 worker evita a corrida no db.create_all() do 1º arranque e poupa RAM (free
# tier = 512 MB); --threads dá concorrência leve sem processos extra.
CMD gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120 run:app
