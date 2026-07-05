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

    @app.cli.command("financeiro-lacunas")
    @click.option("--csv", "csv_path", default=None,
                  help="Grava o relatório neste caminho .csv (por omissão só imprime no terminal).")
    @click.option("--apply", "aplicar", is_flag=True,
                  help="Escreve na BD as sugestões com estado 'ok'. Nunca escreve 'ambíguo'/'sem correspondência'.")
    def financeiro_lacunas_cmd(csv_path, aplicar):
        """Relatório de numero_factura/entidade_emissora em falta (sugestões da Descrição)."""
        from .financeiro_service import relatorio_lacunas_financeiro, aplicar_lacunas_financeiro

        linhas = relatorio_lacunas_financeiro()
        if not linhas:
            click.echo("Nenhum movimento com Nº de factura/Entidade emissora em falta.")
            return

        campos = ["numero_ordem", "descricao", "num_factura_atual", "num_factura_sugerido",
                  "entidade_atual", "entidade_sugerida", "entidade_candidatos", "estado"]

        if csv_path:
            import csv as csv_mod
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv_mod.DictWriter(f, fieldnames=campos)
                writer.writeheader()
                for linha in linhas:
                    writer.writerow({k: linha[k] for k in campos})
            click.echo(f"Relatório gravado em {csv_path} ({len(linhas)} movimentos).")
        else:
            click.echo(f"{'Ordem':>6}  {'Estado':<20}  {'Nº factura (atual → sugerido)':<32}  "
                       f"{'Entidade (atual → sugerida/candidatos)':<45}  Descrição")
            click.echo("-" * 150)
            for linha in linhas:
                factura = f"{linha['num_factura_atual'] or '—'} → {linha['num_factura_sugerido'] or '—'}"
                entidade_sugestao = linha["entidade_sugerida"] or linha["entidade_candidatos"] or "—"
                entidade = f"{linha['entidade_atual'] or '—'} → {entidade_sugestao}"
                click.echo(
                    f"{linha['numero_ordem']:>6}  {linha['estado']:<20}  {factura:<32}  "
                    f"{entidade:<45}  {linha['descricao'][:40]}"
                )

        resumo = {}
        for linha in linhas:
            resumo[linha["estado"]] = resumo.get(linha["estado"], 0) + 1
        click.echo("-" * 40)
        click.echo(f"Total: {len(linhas)}  |  " + "  ".join(f"{k}: {v}" for k, v in resumo.items()))

        if aplicar:
            aplicados = aplicar_lacunas_financeiro(linhas)
            click.echo(f"Aplicadas {aplicados} atualização(ões) à BD (só linhas 'ok').")
        elif resumo.get("ok"):
            click.echo(
                f"{resumo['ok']} linha(s) com sugestão pronta a aplicar. "
                "Corre novamente com --apply para escrever na BD."
            )

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
