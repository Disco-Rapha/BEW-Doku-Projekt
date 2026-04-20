"""Streamlit session_state Verwaltung.

Alle session_state-Keys werden hier zentral definiert und initialisiert.
Idempotent: kann bei jedem Rerun aufgerufen werden.
"""

from __future__ import annotations

import streamlit as st

from ..projects import list_projects


def init() -> None:
    """Initialisiert session_state mit Defaults. Lädt Projektliste beim ersten Aufruf."""
    defaults: dict = {
        "active_project_id": None,
        "projects_list": None,  # None = noch nicht geladen
        "sync_running": False,
        "sync_log": [],
        "nav_page": "Projekte",
    }
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default

    # Projektliste beim ersten Aufruf laden
    if st.session_state.projects_list is None:
        refresh_projects()


def refresh_projects() -> None:
    """Lädt die Projektliste neu aus der DB."""
    st.session_state.projects_list = list_projects()
    # Aktives Projekt validieren (kann durch Archivieren ungültig geworden sein)
    ids = {p["id"] for p in st.session_state.projects_list}
    if st.session_state.active_project_id not in ids:
        st.session_state.active_project_id = None


def get_active_project() -> dict | None:
    """Gibt das aktive Projekt als dict zurück, oder None."""
    pid = st.session_state.get("active_project_id")
    if pid is None:
        return None
    for p in (st.session_state.projects_list or []):
        if p["id"] == pid:
            return p
    return None
