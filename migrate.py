"""Migração idempotente da connect2sun.db existente.

- Adiciona a coluna `client_number` (única) aos clientes e atribui números
  sequenciais (por ordem de id) aos registos que ainda não tenham.
- Normaliza o concelho (coluna `city`): apenas Cascais/Sintra são mantidos,
  qualquer outro valor preenchido passa a "Outro".

Para BDs novas (ex.: produção) não é preciso correr isto — o modelo já cria
a coluna via db.create_all(). Correr com:  python migrate.py
"""
import os
import sqlite3

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "connect2sun.db"))

VALID = {"cascais": "Cascais", "sintra": "Sintra"}


def main():
    if not os.path.exists(DB_PATH):
        print(f"BD não encontrada em {DB_PATH} — nada a migrar.")
        return

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    cols = [r[1] for r in cur.execute("PRAGMA table_info(clients)").fetchall()]

    # 0) coluna locality
    if "locality" not in cols:
        cur.execute("ALTER TABLE clients ADD COLUMN locality TEXT")
        print("+ coluna locality adicionada")

    # 1) coluna client_number
    if "client_number" not in cols:
        cur.execute("ALTER TABLE clients ADD COLUMN client_number INTEGER")
        print("+ coluna client_number adicionada")

    # 2) backfill sequencial para quem não tem número
    rows = cur.execute(
        "SELECT id FROM clients WHERE client_number IS NULL ORDER BY id"
    ).fetchall()
    start = (cur.execute("SELECT MAX(client_number) FROM clients").fetchone()[0] or 0)
    for offset, (cid,) in enumerate(rows, start=1):
        cur.execute(
            "UPDATE clients SET client_number = ? WHERE id = ?", (start + offset, cid)
        )
    if rows:
        print(f"+ {len(rows)} cliente(s) numerado(s) a partir de {start + 1}")

    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_clients_client_number "
        "ON clients (client_number)"
    )

    # 3) normalizar concelhos
    changed = 0
    for cid, city in cur.execute(
        "SELECT id, city FROM clients WHERE city IS NOT NULL AND city != ''"
    ).fetchall():
        norm = VALID.get(city.strip().lower(), "Outro")
        if norm != city:
            cur.execute("UPDATE clients SET city = ? WHERE id = ?", (norm, cid))
            changed += 1
    if changed:
        print(f"+ {changed} concelho(s) normalizado(s)")

    con.commit()
    con.close()
    print("Migração concluída.")


if __name__ == "__main__":
    main()
