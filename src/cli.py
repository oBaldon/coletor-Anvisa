from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from src.collectors.powerbi_normas import PowerBINormasCollector
from src.exporters.url_env_exporter import export_urls_for_rag
from src.jobs.daily_update import run_daily_update, save_decoded_rows
from src.normalizers.normas import normalize_rows
from src.storage.csv_repository import CsvNormasRepository

app = typer.Typer(help="Coletor de normas ANVISA via Power BI público.")
console = Console()


@app.command()
def collect(
    max_pages: int = typer.Option(100, help="Limite de páginas do Power BI."),
    output_dir: Path = typer.Option(Path("data/raw"), help="Diretório para salvar JSON decodificado."),
    save_raw_pages: bool = typer.Option(True, help="Salvar respostas brutas DSR por página."),
) -> None:
    """Coleta dados do Power BI e salva JSON decodificado em data/raw."""
    collector = PowerBINormasCollector()
    rows = collector.collect_all(
        max_pages=max_pages,
        raw_dir=output_dir if save_raw_pages else None,
    )
    decoded_path = save_decoded_rows(rows, output_dir)
    console.print(f"[green]Coleta concluída.[/green] Linhas únicas: {len(rows)}")
    console.print(f"JSON decodificado: {decoded_path}")


@app.command("update-csv")
def update_csv(
    input_json: Path = typer.Argument(..., help="Arquivo JSON decodificado gerado pelo comando collect."),
    csv_path: Path = typer.Option(Path("data/normas.csv"), help="CSV de normas."),
) -> None:
    """Atualiza data/normas.csv a partir de um JSON previamente coletado."""
    rows = json.loads(input_json.read_text(encoding="utf-8"))
    normalized = normalize_rows(rows)
    result = CsvNormasRepository(csv_path).upsert(normalized)
    print_upsert_result(result)


@app.command("export-urls")
def export_urls(
    csv_path: Path = typer.Option(Path("data/normas.csv"), help="CSV de normas."),
    urls_path: Path = typer.Option(Path("data/urls_anvisa.txt"), help="Arquivo de URLs para o RAG."),
    env_path: Path = typer.Option(Path("data/url.env"), help="Arquivo env consumido pelo RAG."),
    status: Optional[str] = typer.Option(None, help="Filtrar por status_ato exato."),
    macrotema: Optional[str] = typer.Option(None, help="Filtrar por macrotema exato."),
) -> None:
    """Gera data/urls_anvisa.txt e data/url.env a partir do CSV."""
    result = export_urls_for_rag(
        csv_path=csv_path,
        urls_path=urls_path,
        env_path=env_path,
        only_status=status,
        only_macrotema=macrotema,
    )
    console.print(f"[green]Exportação concluída.[/green] URLs: {result.urls_count}")
    console.print(f"URLs: {result.urls_path}")
    console.print(f"ENV:  {result.env_path}")


@app.command("run-daily")
def run_daily(
    csv_path: Path = typer.Option(Path("data/normas.csv"), help="CSV de normas."),
    urls_path: Path = typer.Option(Path("data/urls_anvisa.txt"), help="Arquivo de URLs para o RAG."),
    env_path: Path = typer.Option(Path("data/url.env"), help="Arquivo env consumido pelo RAG."),
    max_pages: int = typer.Option(100, help="Limite de páginas do Power BI."),
    raw_dir: Path = typer.Option(Path("data/raw"), help="Diretório para respostas brutas."),
) -> None:
    """Executa fluxo completo: coleta, normaliza, atualiza CSV e exporta URLs."""
    result = run_daily_update(
        csv_path=csv_path,
        urls_path=urls_path,
        env_path=env_path,
        raw_dir=raw_dir,
        max_pages=max_pages,
        export_urls=True,
    )

    console.print(f"[green]Rotina diária concluída.[/green]")
    console.print(f"Coletadas: {result.coletadas}")
    console.print(f"Normalizadas: {result.normalizadas}")
    print_upsert_result(result.csv)

    if result.export:
        console.print(f"URLs exportadas: {result.export.urls_count}")
        console.print(f"Arquivo URLs: {result.export.urls_path}")
        console.print(f"Arquivo ENV:  {result.export.env_path}")


def print_upsert_result(result) -> None:
    table = Table(title="Atualização do CSV")
    table.add_column("Métrica")
    table.add_column("Valor", justify="right")

    table.add_row("Recebidas", str(result.total_recebidas))
    table.add_row("Total CSV", str(result.total_csv))
    table.add_row("Inseridas", str(result.inseridas))
    table.add_row("Atualizadas", str(result.atualizadas))
    table.add_row("Inalteradas", str(result.inalteradas))
    table.add_row("Arquivo", result.csv_path)

    console.print(table)


if __name__ == "__main__":
    app()
