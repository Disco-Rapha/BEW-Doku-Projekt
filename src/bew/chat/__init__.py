"""Chat-Persistenz für den Foundry-Agent.

Threads und Messages werden lokal in bew.db gespiegelt
(Migration 004). Foundry hält die Conversation-History zusätzlich
serverseitig — der lokale Mirror dient für UI-Rendering, Datasette-
Inspektion und Offline-Analyse.
"""

from .repo import (
    append_message,
    archive_thread,
    create_thread,
    delete_thread,
    get_thread,
    get_thread_by_foundry_id,
    list_messages,
    list_threads,
    set_foundry_thread_id,
    update_thread_title,
)

__all__ = [
    "append_message",
    "archive_thread",
    "create_thread",
    "delete_thread",
    "get_thread",
    "get_thread_by_foundry_id",
    "list_messages",
    "list_threads",
    "set_foundry_thread_id",
    "update_thread_title",
]
