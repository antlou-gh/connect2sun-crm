import click

from .models import Client


def register_cli(app):
    """Regista os comandos `flask ...` personalizados do CRM."""

    @app.cli.command("importar-financeiro")
    @click.argument("caminho_xlsx")
    @click.option("--ano", default=2026, show_default=True,
                  help="Ano a atribuir às datas (Dia + Mês da folha).")
    def importar_financeiro_cmd(caminho_xlsx, ano):
        """Importa os movimentos do Excel para a tabela `transacoes` (idempotente)."""
        from .financeiro_service import importar_financeiro
        resumo = importar_financeiro(caminho_xlsx, ano=ano)
        click.echo("── Importação financeira ──────────────────────────────")
        click.echo(f"  Importados ........... {resumo['importados']}")
        click.echo(f"  Já existentes (saltados) {resumo['ja_existentes']}")
        click.echo(f"  Sem cliente associado  {resumo['sem_cliente']}")
        click.echo(f"  Sem categoria .......... {resumo['sem_categoria']}")
        click.echo(f"  Linhas ignoradas ....... {resumo['ignoradas']}")
        if resumo["avisos"]:
            click.echo("── Avisos ──")
            for aviso in resumo["avisos"]:
                click.echo(f"  • {aviso}")

    @app.cli.command("exportar-financeiro")
    @click.argument("ficheiro")
    @click.option("--ano", default=2026, show_default=True, help="Ano a exportar.")
    def exportar_financeiro_cmd(ficheiro, ano):
        """Gera um snapshot Excel das transações no formato da folha do contabilista."""
        from .financeiro_service import gerar_export_financeiro
        wb = gerar_export_financeiro(ano=ano)
        wb.save(ficheiro)
        click.echo(f"Exportado para {ficheiro} (ano {ano}).")

    @app.cli.command("clientes-nif")
    @click.option(
        "--todos",
        is_flag=True,
        help="Listar todos os clientes (por omissão, só os que têm NIF).",
    )
    def clientes_nif(todos):
        """Lista nº + nome + NIF dos clientes, para conferir com a BD Financeira."""
        clientes = Client.query.order_by(Client.client_number.desc()).all()
        if not todos:
            clientes = [c for c in clientes if (c.nif or "").strip()]

        click.echo(f"{'Nº':>6}  {'NIF':<12}  Nome")
        click.echo("-" * 52)
        for c in clientes:
            numero = c.client_number if c.client_number is not None else "—"
            nif = (c.nif or "").strip() or "(sem NIF)"
            click.echo(f"{numero:>6}  {nif:<12}  {c.name}")
        click.echo("-" * 52)

        total = Client.query.count()
        com_nif = Client.query.filter(
            Client.nif.isnot(None), Client.nif != ""
        ).count()
        click.echo(
            f"Mostrados: {len(clientes)} | Total no CRM: {total} | com NIF: {com_nif}"
        )
