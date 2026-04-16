"""Foundry-Agent fuer BEW Doku Projekt.

Oeffentliche API:
  - AgentService: Klasse, die einen Foundry-Thread fuehrt und Custom Functions
    dispatcht. Wird von der WebSocket-Schicht und dem CLI genutzt.
  - FUNCTIONS: Registry aller Custom Functions (Name -> FunctionSpec).
  - get_tool_schemas(): Liste aller Function-Schemas fuer die Foundry-Agent-Registrierung.
  - dispatch(name, arguments): Fuehrt eine Custom Function aus.

Die eigentliche Implementierung der Functions liegt in:
  - functions/domain.py   — 6 bestehende Domain-Tools
  - functions/data.py     — sqlite_query / sqlite_write (Phase 2b)
  - functions/fs.py       — fs_list / fs_read (Phase 2b)
  - functions/pdf.py      — pdf_extract_text (Phase 2b)
  - functions/notes.py    — project_notes_* (Phase 2b)
  - functions/jobs.py     — start_job / job_status (Phase 2c)
"""

from .functions import FUNCTIONS, dispatch, get_tool_schemas

__all__ = ["FUNCTIONS", "dispatch", "get_tool_schemas"]
