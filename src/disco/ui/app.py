"""Streamlit-Einstiegspunkt.

Starten mit:
    uv run streamlit run src/bew/ui/app.py
"""

from __future__ import annotations

import streamlit as st

from .state import get_active_project, init
from .pages import projects as projects_page
from .pages import sources as sources_page
from .pages import documents as documents_page


def main() -> None:
    st.set_page_config(
        page_title="BEW Doku Projekt",
        page_icon="📄",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    init()

    # ----------------------------------------------------------------
    # Sidebar
    # ----------------------------------------------------------------
    with st.sidebar:
        st.title("📄 BEW Doku")
        st.caption("Agentisches Dokumenten-Management")

        page = st.radio(
            "Navigation",
            ["Projekte", "Quellen", "Dokumente"],
            key="nav_page",
        )

        # Aktives Projekt anzeigen
        active = get_active_project()
        if active:
            st.divider()
            st.success(f"Aktives Projekt:\n**{active['name']}**")
            if st.button("Projekt wechseln", key="change_project"):
                st.session_state.active_project_id = None
                st.session_state.nav_page = "Projekte"
                st.rerun()
        else:
            st.divider()
            st.warning("Kein Projekt ausgewählt")

    # ----------------------------------------------------------------
    # Seiteninhalt
    # ----------------------------------------------------------------
    if page == "Projekte":
        projects_page.render()
    elif page == "Quellen":
        sources_page.render()
    elif page == "Dokumente":
        documents_page.render()


if __name__ == "__main__":
    main()
