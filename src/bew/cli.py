"""CLI-Einstieg: `bew <kommando>` oder `python -m bew <kommando>`."""

from __future__ import annotations

import json
from pathlib import Path

import click

from . import __version__, db as db_module
from . import projects as projects_module
from . import sources as sources_module


@click.group()
@click.version_option(__version__, prog_name="bew")
def main() -> None:
    """BEW Doku Projekt — agentisches Dokumenten-Management-System."""


# ---------------------------------------------------------------------------
# bew db
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# bew project
# ---------------------------------------------------------------------------

@main.group("project")
def project_group() -> None:
    """Projekt-Kommandos."""


@project_group.command("list")
@click.option("--all", "include_archived", is_flag=True, default=False, help="Auch archivierte Projekte anzeigen.")
def project_list(include_archived: bool) -> None:
    """Listet alle Projekte auf."""
    items = projects_module.list_projects(include_archived=include_archived)
    if not items:
        click.echo("Keine Projekte vorhanden. Mit 'bew project create' anlegen.")
        return
    click.echo(f"{'ID':<5} {'Name':<30} {'Status':<12} Erstellt")
    click.echo("-" * 65)
    for p in items:
        click.echo(f"{p['id']:<5} {p['name']:<30} {p['status']:<12} {p['created_at'][:10]}")


@project_group.command("create")
@click.option("--name", required=True, help="Name des Projekts.")
@click.option("--description", default=None, help="Optionale Beschreibung.")
def project_create(name: str, description: str | None) -> None:
    """Legt ein neues Projekt an."""
    try:
        p = projects_module.create_project(name, description)
        click.echo(f"Projekt angelegt: ID={p['id']}, Name='{p['name']}'")
    except ValueError as exc:
        click.echo(f"Fehler: {exc}", err=True)
        raise SystemExit(1)


@project_group.command("archive")
@click.option("--id", "project_id", required=True, type=int, help="Projekt-ID.")
def project_archive(project_id: int) -> None:
    """Archiviert ein Projekt (reversibel — Daten bleiben erhalten)."""
    projects_module.archive_project(project_id)
    click.echo(f"Projekt {project_id} archiviert.")


# ---------------------------------------------------------------------------
# bew source
# ---------------------------------------------------------------------------

@main.group("source")
def source_group() -> None:
    """Quellen-Kommandos."""


@source_group.command("list")
@click.option("--project", "project_id", required=True, type=int, help="Projekt-ID.")
def source_list(project_id: int) -> None:
    """Listet alle Quellen eines Projekts auf."""
    items = sources_module.list_sources(project_id)
    if not items:
        click.echo(f"Keine Quellen in Projekt {project_id}. Mit 'bew source add' hinzufügen.")
        return
    click.echo(f"{'ID':<5} {'Name':<25} {'Typ':<25} {'Status':<10} Zuletzt synchronisiert")
    click.echo("-" * 85)
    for s in items:
        last_sync = s["last_synced_at"][:16] if s["last_synced_at"] else "noch nie"
        click.echo(f"{s['id']:<5} {s['name']:<25} {s['source_type']:<25} {s['status']:<10} {last_sync}")


@source_group.command("add")
@click.option("--project", "project_id", required=True, type=int, help="Projekt-ID.")
@click.option("--name", required=True, help="Anzeigename der Quelle.")
@click.option("--site-url", required=True, help="SharePoint-Site-URL (z.B. https://tenant.sharepoint.com/sites/MySite).")
@click.option("--library", required=True, help="Name der SharePoint-Bibliothek (z.B. 'Dokumente').")
def source_add(project_id: int, name: str, site_url: str, library: str) -> None:
    """Fügt eine SharePoint-Bibliothek als Quelle hinzu."""
    try:
        s = sources_module.create_source(project_id, name, site_url, library)
        click.echo(f"Quelle angelegt: ID={s['id']}, Name='{s['name']}'")
        click.echo(f"  Site-URL:   {site_url}")
        click.echo(f"  Bibliothek: {library}")
        click.echo("Tipp: 'uv run bew sync run --source <ID>' startet die erste Synchronisation.")
    except ValueError as exc:
        click.echo(f"Fehler: {exc}", err=True)
        raise SystemExit(1)


@source_group.command("show")
@click.option("--id", "source_id", required=True, type=int, help="Quellen-ID.")
def source_show(source_id: int) -> None:
    """Zeigt Details und Konfiguration einer Quelle."""
    try:
        s = sources_module.get_source(source_id)
        cfg = sources_module.parse_config(s)
        doc_count = sources_module.count_documents(source_id)
        click.echo(f"ID:            {s['id']}")
        click.echo(f"Name:          {s['name']}")
        click.echo(f"Projekt:       {s['project_id']}")
        click.echo(f"Typ:           {s['source_type']}")
        click.echo(f"Status:        {s['status']}")
        click.echo(f"Dokumente:     {doc_count}")
        click.echo(f"Letzter Sync:  {s['last_synced_at'] or 'noch nie'}")
        click.echo("Konfiguration:")
        click.echo(json.dumps(cfg, indent=2, ensure_ascii=False))
    except KeyError as exc:
        click.echo(f"Fehler: {exc}", err=True)
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# bew sync
# ---------------------------------------------------------------------------

@main.group("sync")
def sync_group() -> None:
    """Synchronisations-Kommandos."""


@sync_group.command("run")
@click.option("--source", "source_id", required=True, type=int, help="Quellen-ID.")
def sync_run(source_id: int) -> None:
    """Startet die Synchronisation einer Quelle mit SharePoint."""
    from .sharepoint.sync import SharePointSyncer
    from .sharepoint.auth import MSALTokenManager
    from .sharepoint.graph import GraphClient
    from .config import settings

    if not settings.msal_tenant_id or not settings.msal_client_id:
        click.echo(
            "Fehler: MSAL_TENANT_ID und MSAL_CLIENT_ID müssen in .env gesetzt sein.",
            err=True,
        )
        raise SystemExit(1)

    try:
        source = sources_module.get_source(source_id)
    except KeyError as exc:
        click.echo(f"Fehler: {exc}", err=True)
        raise SystemExit(1)

    token_mgr = MSALTokenManager(settings.msal_tenant_id, settings.msal_client_id)
    graph = GraphClient(token_mgr)
    from .db import connect
    conn = connect()
    try:
        syncer = SharePointSyncer(conn, graph, source)
        click.echo(f"Starte Sync für Quelle '{source['name']}' (ID {source_id}) ...")
        result = syncer.run()
        click.echo(f"Sync abgeschlossen:")
        click.echo(f"  Ordner aktualisiert: {result.folders_upserted}")
        click.echo(f"  Dateien neu:         {result.files_new}")
        click.echo(f"  Dateien aktualisiert:{result.files_updated}")
        click.echo(f"  Dateien übersprungen:{result.files_skipped}")
        click.echo(f"  Fehler:              {result.files_failed}")
        if result.errors:
            click.echo("Fehlerdetails:")
            for err in result.errors[:10]:
                click.echo(f"  - {err}")
    finally:
        conn.close()


@sync_group.command("status")
@click.option("--source", "source_id", required=True, type=int, help="Quellen-ID.")
def sync_status(source_id: int) -> None:
    """Zeigt den letzten Sync-Status einer Quelle."""
    try:
        s = sources_module.get_source(source_id)
        doc_count = sources_module.count_documents(source_id)
        click.echo(f"Quelle:        {s['name']} (ID {s['id']})")
        click.echo(f"Status:        {s['status']}")
        click.echo(f"Letzter Sync:  {s['last_synced_at'] or 'noch nie'}")
        click.echo(f"Dokumente:     {doc_count}")
    except KeyError as exc:
        click.echo(f"Fehler: {exc}", err=True)
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# bew auth
# ---------------------------------------------------------------------------

@main.group("auth")
def auth_group() -> None:
    """Authentifizierungs-Kommandos (Microsoft Entra ID / SharePoint)."""


@auth_group.command("login")
def auth_login() -> None:
    """Startet den Device-Flow-Login für Microsoft 365."""
    from .sharepoint.auth import MSALTokenManager
    from .config import settings

    if not settings.msal_tenant_id or not settings.msal_client_id:
        click.echo(
            "Fehler: MSAL_TENANT_ID und MSAL_CLIENT_ID müssen in .env gesetzt sein.",
            err=True,
        )
        raise SystemExit(1)

    mgr = MSALTokenManager(settings.msal_tenant_id, settings.msal_client_id)
    click.echo("Starte Authentifizierung ...")
    token = mgr.get_token(force_interactive=True)
    if token:
        click.echo("Erfolgreich angemeldet. Token wurde lokal gespeichert.")
    else:
        click.echo("Anmeldung fehlgeschlagen.", err=True)
        raise SystemExit(1)


@auth_group.command("status")
def auth_status() -> None:
    """Prüft ob ein gültiges Token im Cache liegt."""
    from .sharepoint.auth import MSALTokenManager
    from .config import settings

    if not settings.msal_tenant_id or not settings.msal_client_id:
        click.echo("MSAL_TENANT_ID / MSAL_CLIENT_ID nicht konfiguriert.")
        return

    mgr = MSALTokenManager(settings.msal_tenant_id, settings.msal_client_id)
    if mgr.is_authenticated():
        click.echo("Status: Angemeldet (Token im Cache vorhanden).")
    else:
        click.echo("Status: Nicht angemeldet. 'uv run bew auth login' ausführen.")


@auth_group.command("logout")
def auth_logout() -> None:
    """Löscht den lokalen Token-Cache (erzwingt nächsten Login)."""
    from .sharepoint.auth import MSALTokenManager
    from .config import settings

    if not settings.msal_tenant_id or not settings.msal_client_id:
        click.echo("MSAL_TENANT_ID / MSAL_CLIENT_ID nicht konfiguriert.")
        return

    mgr = MSALTokenManager(settings.msal_tenant_id, settings.msal_client_id)
    mgr.clear_cache()
    click.echo("Token-Cache gelöscht.")


# ---------------------------------------------------------------------------
# bew sp  (SharePoint-Hilfswerkzeuge ohne Graph-API)
# ---------------------------------------------------------------------------

@main.group("sp")
def sp_group() -> None:
    """SharePoint-Hilfswerkzeuge (REST-API, kein Graph-API-Zugang nötig)."""


@sp_group.command("import-json")
@click.argument("json_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--source", "source_id", required=True, type=int, help="Quellen-ID in der DB.")
def sp_import_json(json_file: "Path", source_id: int) -> None:
    """Importiert einen SharePoint REST-API JSON-Export in die DB.

    JSON_FILE: Pfad zur exportierten JSON-Datei (Browser-Script-Output).

    Beispiel:\n
        uv run bew sp import-json sp_export_Dokumente_123.json --source 1
    """
    from pathlib import Path as _Path
    from .sharepoint.import_json import SharePointJSONImporter
    from .db import connect

    json_path = _Path(json_file)
    conn = connect()
    try:
        importer = SharePointJSONImporter(conn, source_id)
        click.echo(f"Importiere '{json_path.name}' → Quelle {source_id} ...")
        click.echo(f"  Library-Prefix: {importer._library_prefix or '(wird aus Daten erkannt)'}")
        result = importer.run(json_path)
        click.echo("Import abgeschlossen:")
        click.echo(f"  Ordner:          {result.folders_upserted}")
        click.echo(f"  Dateien neu:     {result.files_new}")
        click.echo(f"  Aktualisiert:    {result.files_updated}")
        if result.errors:
            click.echo(f"  Fehler:          {len(result.errors)}")
            for err in result.errors[:10]:
                click.echo(f"    - {err}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
