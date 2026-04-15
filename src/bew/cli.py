"""CLI-Einstieg: `bew <kommando>` oder `python -m bew <kommando>`."""

from __future__ import annotations

import click

from . import __version__, db as db_module


@click.group()
@click.version_option(__version__, prog_name="bew")
def main() -> None:
    """BEW Doku Projekt — lokale PDF-Pipeline."""


@main.group("db")
def db_group() -> None:
    """Datenbank-Kommandos."""


@db_group.command("init")
def db_init() -> None:
    """Legt die SQLite-DB an und wendet ausstehende Migrationen an."""
    result = db_module.init_db()
    click.echo(f"DB: {result['db_path']}")
    if result["applied"]:
        versions = ", ".join(f"v{v}" for v in result["applied"])
        click.echo(f"Angewendet: {versions}")
    else:
        click.echo("Keine neuen Migrationen.")
    click.echo(f"Aktuelle Schema-Version: v{result['current_version']}")


@db_group.command("status")
def db_status() -> None:
    """Zeigt Schema-Version und Tabellenliste."""
    result = db_module.status()
    if not result.get("exists"):
        click.echo(f"DB nicht gefunden: {result['db_path']}")
        click.echo("Tipp: 'uv run bew db init' ausführen.")
        return
    click.echo(f"DB: {result['db_path']}")
    click.echo(f"Schema-Version: v{result['current_version']}")
    click.echo("Tabellen:")
    for t in result["tables"]:
        click.echo(f"  - {t}")


if __name__ == "__main__":
    main()
