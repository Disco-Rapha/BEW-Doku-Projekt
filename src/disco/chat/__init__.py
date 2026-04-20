"""Chat-Persistenz fuer den Foundry-Agent.

Ein Projekt = ein persistenter Chat. Messages werden in der system.db
gehalten, bei Kompression via is_compacted=1 als archiviert markiert
(nicht geloescht). Der letzte Foundry-Response-Handle fuer
previous_response_id liegt in project_chat_state.
"""

from .repo import (
    append_message,
    delete_state,
    get_or_create_state,
    get_state,
    last_active_message_id,
    list_active_messages,
    list_all_messages,
    mark_compacted,
    recompute_token_estimate,
    set_response_id,
    update_token_estimate,
)

__all__ = [
    "append_message",
    "delete_state",
    "get_or_create_state",
    "get_state",
    "last_active_message_id",
    "list_active_messages",
    "list_all_messages",
    "mark_compacted",
    "recompute_token_estimate",
    "set_response_id",
    "update_token_estimate",
]
