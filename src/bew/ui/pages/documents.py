"""Streamlit-Seite: Dokumente & Ordnerbaum."""

from __future__ import annotations

import streamlit as st

from ...db import connect
from ...sources import get_all_folders, list_sources
from ..state import get_active_project


def render() -> None:
    project = get_active_project()
    if project is None:
        st.warning("Bitte zuerst ein Projekt auswählen (Seite: Projekte).")
        return

    st.header(f"Dokumente — {project['name']}")

    sources = list_sources(project["id"])
    if not sources:
        st.info("Keine Quellen vorhanden. Zuerst eine SharePoint-Bibliothek hinzufügen.")
        return

    # Quell-Auswahl
    source_options = {s["id"]: s["name"] for s in sources}
    selected_source_id = st.selectbox(
        "Quelle",
        options=list(source_options.keys()),
        format_func=lambda sid: source_options[sid],
        key="doc_source_id",
    )

    if selected_source_id is None:
        return

    # Suchfeld
    search_term = st.text_input("Suche", placeholder="Dateiname ...")

    # Layout: Ordnerbaum links, Dokumente rechts
    col_tree, col_docs = st.columns([1, 2])

    with col_tree:
        st.subheader("Ordner")
        selected_folder_id = _render_folder_tree(selected_source_id)

    with col_docs:
        st.subheader("Dateien")
        _render_documents(
            project["id"],
            selected_source_id,
            folder_id=selected_folder_id,
            search=search_term,
        )


def _render_folder_tree(source_id: int) -> int | None:
    """Rendert den Ordnerbaum als verschachtelte Expander.

    Returns:
        ID des ausgewählten Ordners, oder None für "alle".
    """
    folders = get_all_folders(source_id)
    if not folders:
        st.caption("Noch keine Ordner. Sync starten.")
        return None

    # Baum aufbauen: parent_id → [children]
    children: dict[int | None, list[dict]] = {}
    for f in folders:
        parent = f["parent_id"]
        children.setdefault(parent, []).append(f)

    if "selected_folder_id" not in st.session_state:
        st.session_state.selected_folder_id = None

    # "Alle" Button
    if st.button(
        "Alle Dokumente",
        key="folder_all",
        type="primary" if st.session_state.selected_folder_id is None else "secondary",
    ):
        st.session_state.selected_folder_id = None
        st.rerun()

    _render_folder_nodes(children, parent_id=None, depth=0)
    return st.session_state.selected_folder_id


def _render_folder_nodes(
    children: dict[int | None, list[dict]],
    parent_id: int | None,
    depth: int,
) -> None:
    """Rekursiver Ordnerbaum-Renderer."""
    for folder in children.get(parent_id, []):
        has_children = folder["id"] in children
        label = ("  " * depth) + ("📁 " if has_children else "📄 ") + folder["name"]

        is_selected = st.session_state.get("selected_folder_id") == folder["id"]
        if st.button(
            label,
            key=f"folder_{folder['id']}",
            type="primary" if is_selected else "secondary",
        ):
            st.session_state.selected_folder_id = folder["id"]
            st.rerun()

        if has_children:
            _render_folder_nodes(children, parent_id=folder["id"], depth=depth + 1)


def _render_documents(
    project_id: int,
    source_id: int,
    folder_id: int | None,
    search: str,
) -> None:
    """Zeigt Dokumente für den ausgewählten Ordner und Suchbegriff."""
    conn = connect()
    try:
        # Basis-Query
        params: list = [project_id, source_id]
        where_clauses = ["d.project_id = ?", "d.source_id = ?"]

        if folder_id is not None:
            # Alle Dokumente deren source_path in diesem Ordner liegt
            folder_row = conn.execute(
                "SELECT sp_path FROM source_folders WHERE id = ?", (folder_id,)
            ).fetchone()
            if folder_row:
                where_clauses.append("d.source_path LIKE ?")
                params.append(folder_row["sp_path"] + "%")

        if search.strip():
            where_clauses.append("d.original_name LIKE ?")
            params.append(f"%{search.strip()}%")

        where_sql = " AND ".join(where_clauses)
        rows = conn.execute(
            f"""
            SELECT d.id, d.original_name, d.size_bytes, d.status,
                   d.source_path, d.created_at
            FROM documents d
            WHERE {where_sql}
            ORDER BY d.original_name
            LIMIT 500
            """,
            params,
        ).fetchall()

        if not rows:
            st.info("Keine Dokumente gefunden.")
            return

        st.caption(f"{len(rows)} Dokument(e)")

        # Tabelle
        for row in rows:
            with st.container():
                c1, c2, c3 = st.columns([4, 1, 1])
                with c1:
                    st.text(row["original_name"])
                    if row["source_path"]:
                        st.caption(row["source_path"])
                with c2:
                    size_kb = (row["size_bytes"] or 0) // 1024
                    st.caption(f"{size_kb} KB")
                with c3:
                    status_color = {"registered": "🔵", "parsed": "🟢", "failed": "🔴"}.get(
                        row["status"], "⚪"
                    )
                    st.caption(f"{status_color} {row['status']}")
    finally:
        conn.close()
