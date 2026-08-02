"""Testes ao estado das migrações do Alembic.

Guardam o risco introduzido quando o `alembic upgrade head` passou a correr
sozinho no arranque do contentor (ver Dockerfile): uma migração incompleta
deixaria produção com um esquema diferente do que os modelos declaram, e nada
avisaria. Estes testes correm as migrações de raiz numa base descartável e
comparam o resultado com o metadata do SQLAlchemy.

Precisam de um PostgreSQL local acessível por socket Unix com peer auth
(ver README). Sem ele, são ignorados em vez de falharem — nem toda a gente
que corre a suite tem Postgres instalado.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
BD_TESTE = "crm_test_migracoes"
URL_TESTE = f"postgresql:///{BD_TESTE}"


def _ha_postgres_local():
    try:
        r = subprocess.run(
            ["psql", "-d", "postgres", "-Atc", "SELECT 1"],
            capture_output=True,
            timeout=10,
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


requer_postgres = pytest.mark.skipif(
    not _ha_postgres_local(),
    reason="sem PostgreSQL local acessível por socket Unix",
)


@pytest.fixture
def bd_vazia():
    """Base de dados descartável, criada com o mesmo locale que produção."""
    subprocess.run(["dropdb", "--if-exists", "--force", BD_TESTE], check=True)
    subprocess.run(
        [
            "createdb",
            BD_TESTE,
            "--template=template0",
            "--encoding=UTF8",
            "--locale=C.UTF-8",
        ],
        check=True,
    )
    yield URL_TESTE
    subprocess.run(["dropdb", "--if-exists", "--force", BD_TESTE], check=True)


def _alembic(*args, url):
    """Corre o alembic num subprocesso, para não poluir o processo dos testes.

    O `migrations/env.py` chama create_app() ao ser importado, o que criaria
    uma segunda app Flask dentro da suite; num subprocesso isso é irrelevante.
    """
    ambiente = {**os.environ, "DATABASE_URL": url}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=RAIZ,
        env=ambiente,
        capture_output=True,
        text=True,
    )


@requer_postgres
def test_upgrade_de_raiz_funciona(bd_vazia):
    """`alembic upgrade head` numa base vazia corre sem erros."""
    r = _alembic("upgrade", "head", url=bd_vazia)
    assert r.returncode == 0, f"upgrade falhou:\n{r.stderr}"

    actual = _alembic("current", url=bd_vazia)
    assert "(head)" in actual.stdout, f"não ficou em head:\n{actual.stdout}"


@requer_postgres
def test_migracoes_cobrem_os_modelos(bd_vazia):
    """Depois do upgrade, o autogenerate não tem nada a propor.

    Se este teste falhar, há um modelo alterado sem a migração correspondente.
    A saída do comando mostra o que está a divergir.
    """
    r = _alembic("upgrade", "head", url=bd_vazia)
    assert r.returncode == 0, f"upgrade falhou:\n{r.stderr}"

    r = _alembic("check", url=bd_vazia)
    assert r.returncode == 0, (
        "o esquema das migrações não coincide com os modelos — "
        f"falta gerar uma migração:\n{r.stdout}\n{r.stderr}"
    )


@requer_postgres
def test_downgrade_reverte_tudo(bd_vazia):
    """`downgrade base` deixa a base sem tabelas da aplicação.

    Sem isto, uma migração pode ter um upgrade correcto e um downgrade partido,
    e só se descobre no dia em que for preciso reverter.
    """
    assert _alembic("upgrade", "head", url=bd_vazia).returncode == 0

    r = _alembic("downgrade", "base", url=bd_vazia)
    assert r.returncode == 0, f"downgrade falhou:\n{r.stderr}"

    sobras = subprocess.run(
        [
            "psql",
            "-d",
            BD_TESTE,
            "-Atc",
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name <> 'alembic_version' "
            "ORDER BY 1",
        ],
        capture_output=True,
        text=True,
    ).stdout.split()
    assert sobras == [], f"tabelas deixadas para trás pelo downgrade: {sobras}"
