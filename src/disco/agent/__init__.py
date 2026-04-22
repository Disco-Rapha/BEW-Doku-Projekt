"""Disco-Agent (Foundry/GPT-5).

Oeffentliche API:
  - AgentService: Klasse, die einen Foundry-Thread fuehrt und Custom Functions
    dispatcht. Wird von der WebSocket-Schicht und dem CLI genutzt.
  - FUNCTIONS: Registry aller Custom Functions (Name -> FunctionSpec).
  - get_tool_schemas(): Liste aller Function-Schemas fuer die Foundry-Agent-Registrierung.
  - dispatch(name, arguments): Fuehrt eine Custom Function aus.

Die eigentliche Implementierung der Functions liegt in
`functions/`. Die vollstaendige Liste der registrierten Tools ergibt
sich aus `FUNCTIONS` zur Laufzeit; ein Blick in
`functions/__init__.py` zeigt, welche Submodule beim Import geladen
werden.
"""

from .functions import FUNCTIONS, dispatch, get_tool_schemas

__all__ = ["FUNCTIONS", "dispatch", "get_tool_schemas"]
