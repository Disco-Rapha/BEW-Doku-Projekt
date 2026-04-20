"""Streamlit-Seite: Quellen & Synchronisation."""

from __future__ import annotations

import streamlit as st

from ...config import settings
from ...db import connect
from ...sources import (
    count_documents,
    create_source,
    get_source,
    list_sources,
    parse_config,
)
from ...sharepoint.auth import MSALTokenManager, MSALAuthError
from ...sharepoint.graph import GraphClient
from ...sharepoint.sync import SharePointSyncer, SyncError
from ..state import get_active_project


def render() -> None:
    project = get_active_project()
    if project is None:
        st.warning("Bitte zuerst ein Projekt auswählen (Seite: Projekte).")
        return

    st.header(f"Quellen — {project['name']}")

    # ----------------------------------------------------------------
    # MSAL-Konfiguration prüfen
    # ----------------------------------------------------------------
    msal_ok = bool(settings.msal_tenant_id and settings.msal_client_id)
    if not msal_ok:
        st.error(
            "MSAL_TENANT_ID und MSAL_CLIENT_ID sind nicht in .env konfiguriert. "
            "Bitte .env.example als Vorlage verwenden."
        )

    # ----------------------------------------------------------------
    # Login-Status
    # ----------------------------------------------------------------
    with st.expander("Microsoft 365 Anmeldestatus", expanded=False):
        _render_auth_section()

    # ----------------------------------------------------------------
    # Vorhandene Quellen
    # ----------------------------------------------------------------
    sources = list_sources(project["id"])

    if sources:
        st.subheader(f"{len(sources)} Quelle(n)")
        for s in sources:
            cfg = parse_config(s)
            doc_count = count_documents(s["id"])
            with st.container(border=True):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.markdown(f"**{s['name']}**")
                    st.caption(
                        f"Site: {cfg.get('site_url', '—')} · "
                        f"Bibliothek: {cfg.get('library_name', '—')}"
                    )
                    last = s["last_synced_at"]
                    if last:
                        st.caption(f"Letzter Sync: {last[:16]}")
                    else:
                        st.caption("Noch nie synchronisiert")
                with col2:
                    st.metric("Dokumente", doc_count)
                    if st.button("Sync starten", key=f"sync_{s['id']}", disabled=not msal_ok):
                        _run_sync(s["id"])
    else:
        st.info("Noch keine Quellen. Unten eine SharePoint-Bibliothek hinzufügen.")

    # ----------------------------------------------------------------
    # Neue SharePoint-Quelle hinzufügen
    # ----------------------------------------------------------------
    st.divider()
    with st.expander("SharePoint-Bibliothek hinzufügen", expanded=not sources):
        with st.form("new_source_form", clear_on_submit=True):
            name = st.text_input("Anzeigename *", placeholder="z.B. Technische Dokumentation")
            site_url = st.text_input(
                "SharePoint-Site-URL *",
                placeholder="https://tenant.sharepoint.com/sites/MySite",
            )
            library = st.text_input(
                "Bibliotheksname *",
                placeholder="Dokumente",
                value="Dokumente",
            )
            submitted = st.form_submit_button("Quelle hinzufügen", type="primary")

        if submitted:
            errors = []
            if not name.strip():
                errors.append("Name fehlt.")
            if not site_url.strip().startswith("http"):
                errors.append("Bitte eine vollständige Site-URL angeben (https://...).")
            if not library.strip():
                errors.append("Bibliotheksname fehlt.")
            if errors:
                for e in errors:
                    st.error(e)
            else:
                try:
                    s = create_source(
                        project["id"],
                        name.strip(),
                        site_url.strip(),
                        library.strip(),
                    )
                    st.success(
                        f"Quelle '{s['name']}' angelegt (ID {s['id']}). "
                        "Jetzt 'Sync starten' klicken."
                    )
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _render_auth_section() -> None:
    """Zeigt Login-Status und Device-Flow-Button."""
    if not settings.msal_tenant_id or not settings.msal_client_id:
        st.warning("MSAL nicht konfiguriert.")
        return

    mgr = MSALTokenManager(settings.msal_tenant_id, settings.msal_client_id)

    if mgr.is_authenticated():
        username = mgr.get_username() or "Unbekannt"
        st.success(f"Angemeldet als: {username}")
        if st.button("Abmelden (Token löschen)"):
            mgr.clear_cache()
            st.rerun()
    else:
        st.warning("Nicht angemeldet.")
        if st.button("Jetzt anmelden (Browser-Login)"):
            st.info("Warte auf Login ...")
            try:
                # Device Flow gibt Anweisung auf stdout aus — hier fangen wir sie ab
                import io
                import sys
                buf = io.StringIO()
                sys_stdout = sys.stdout
                sys.stdout = buf
                try:
                    mgr.get_token(force_interactive=True)
                finally:
                    sys.stdout = sys_stdout
                flow_msg = buf.getvalue()
                if flow_msg:
                    st.code(flow_msg)
                st.success("Erfolgreich angemeldet!")
                st.rerun()
            except MSALAuthError as exc:
                st.error(f"Anmeldung fehlgeschlagen: {exc}")


def _run_sync(source_id: int) -> None:
    """Startet den Sync einer Quelle und zeigt Fortschritt."""
    if not settings.msal_tenant_id or not settings.msal_client_id:
        st.error("MSAL nicht konfiguriert.")
        return

    try:
        source = get_source(source_id)
    except KeyError as exc:
        st.error(str(exc))
        return

    mgr = MSALTokenManager(settings.msal_tenant_id, settings.msal_client_id)
    graph = GraphClient(mgr)
    conn = connect()

    try:
        with st.spinner(f"Sync läuft: {source['name']} ..."):
            syncer = SharePointSyncer(conn, graph, source)
            result = syncer.run()

        st.success(
            f"Sync abgeschlossen: "
            f"{result.files_new} neu, "
            f"{result.files_updated} aktualisiert, "
            f"{result.files_skipped} übersprungen, "
            f"{result.folders_upserted} Ordner."
        )
        if result.errors:
            with st.expander(f"{result.files_failed} Fehler"):
                for err in result.errors:
                    st.text(err)
        st.rerun()
    except SyncError as exc:
        st.error(f"Sync fehlgeschlagen: {exc}")
    finally:
        conn.close()
