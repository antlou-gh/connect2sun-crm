import click

from .models import Client


def register_cli(app):
    """Regista os comandos `flask ...` personalizados do CRM."""

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
