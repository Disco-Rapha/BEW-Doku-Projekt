"""Streamlit-Seite: Projekte."""

from __future__ import annotations

import streamlit as st

from ...projects import archive_project, count_documents, create_project
from ..state import refresh_projects


def render() -> None:
    st.header("Projekte")

    projects = st.session_state.projects_list or []

    # ----------------------------------------------------------------
    # Tabelle vorhandener Projekte
    # ----------------------------------------------------------------
    if projects:
        st.subheader(f"{len(projects)} Projekt(e)")
        for p in projects:
            with st.container(border=True):
                col1, col2, col3 = st.columns([4, 2, 1])
                with col1:
                    st.markdown(f"**{p['name']}**")
                    if p.get("description"):
                        st.caption(p["description"])
                with col2:
                    doc_count = count_documents(p["id"])
                    st.metric("Dokumente", doc_count)
                with col3:
                    if st.button(
                        "Auswählen",
                        key=f"select_{p['id']}",
                        type="primary" if st.session_state.active_project_id == p["id"] else "secondary",
                    ):
                        st.session_state.active_project_id = p["id"]
                        st.rerun()

                    if st.button("Archivieren", key=f"archive_{p['id']}"):
                        archive_project(p["id"])
                        if st.session_state.active_project_id == p["id"]:
                            st.session_state.active_project_id = None
                        refresh_projects()
                        st.rerun()
    else:
        st.info("Noch keine Projekte vorhanden. Legen Sie unten ein neues an.")

    # ----------------------------------------------------------------
    # Neues Projekt anlegen
    # ----------------------------------------------------------------
    st.divider()
    with st.expander("Neues Projekt anlegen", expanded=not projects):
        with st.form("new_project_form", clear_on_submit=True):
            name = st.text_input("Name *", placeholder="z.B. BEW-Dokumentation 2024")
            description = st.text_area(
                "Beschreibung (optional)",
                placeholder="Kurze Beschreibung des Projekts",
                height=80,
            )
            submitted = st.form_submit_button("Projekt anlegen", type="primary")

        if submitted:
            if not name.strip():
                st.error("Bitte einen Projektnamen eingeben.")
            else:
                try:
                    p = create_project(name.strip(), description.strip() or None)
                    st.session_state.active_project_id = p["id"]
                    refresh_projects()
                    st.success(f"Projekt '{p['name']}' angelegt (ID {p['id']}).")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
