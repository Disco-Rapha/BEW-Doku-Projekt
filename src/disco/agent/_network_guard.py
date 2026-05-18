"""Disco Network-Egress-Guard fuer Subprocesses.

Wird in jedem run_python- oder Flow-Subprocess via `_run_with_guard.py`
geladen. Patched die Standard-Lib-Sockets so, dass Verbindungen zu nicht
gewhitelisteten Hosts mit `PermissionError` scheitern. Verstoesse werden
in `agent_egress_violations` (system.db) protokolliert.

**Wie funktioniert's:**
    1. `socket.getaddrinfo(host, ...)` ist der Haupt-Eintrittspunkt fuer
       DNS-Aufloesung. Hier prueft der Guard den Hostname gegen die
       Whitelist (mit fnmatch-Wildcards). Treffer = aufloesen, alle
       gelieferten IPs in `_allowed_ips`-Cache merken. Kein Treffer =
       `PermissionError`.
    2. `socket.socket.connect((host, port))` faengt direkte IP-Calls ab
       (selten, aber moeglich). Loopback wird IMMER erlaubt, sonst muss
       die IP im Cache aus Schritt 1 sein.
    3. `socket.create_connection((host, port))` ist redundant gepatcht
       (Belt + Suspenders).

**Whitelist-Format:** Liste von fnmatch-Pattern-Strings, z.B.
    ["*.openai.azure.com", "*.cognitiveservices.azure.com", "localhost"]

Loopback (127.0.0.0/8, ::1, "localhost") ist IMMER erlaubt, auch wenn
nicht in der Whitelist.

**Audit-Schreibvorgang:** direkt via `sqlite3.connect(system.db)`. KEIN
ORM, KEIN Disco-Code, weil der Guard auch in Subprocesses laeuft, die
Disco-Module nicht voll geladen haben.
"""

from __future__ import annotations

import fnmatch
import os
import socket
import sqlite3
import threading
import traceback
from typing import Any

# Originale-Funktionen, die wir patchen (vor erstem install_guard noch
# unveraendert). Werden in install_guard() ersetzt.
_original_getaddrinfo = socket.getaddrinfo
_original_socket_connect = socket.socket.connect
_original_create_connection = socket.create_connection

# Cache aller IPs, die ueber einen whitelisted Hostname aufgeloest wurden.
# Damit erlaubt `connect((ip, port))` die IP, ohne den Hostname zu kennen.
_allowed_ips: set[str] = set()
_lock = threading.Lock()

# Globaler Guard-State (per Subprocess gesetzt durch install_guard).
_whitelist: list[str] = []
_source: str = "other"
_system_db_path: str | None = None
_project_slug: str | None = None
_guard_installed = False

# Loopback wird IMMER erlaubt. RFC 1122 (127.0.0.0/8) und IPv6 ::1.
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _is_loopback(host: str | None) -> bool:
    if not host:
        return False
    if host in _LOOPBACK_HOSTS:
        return True
    # 127.0.0.0/8
    if host.startswith("127."):
        return True
    return False


def _matches_whitelist(host: str | None) -> bool:
    """Prueft Hostname gegen Whitelist (fnmatch) plus Loopback-Sonderfall."""
    if not host:
        return False
    if _is_loopback(host):
        return True
    host_lower = host.lower()
    for pattern in _whitelist:
        if fnmatch.fnmatch(host_lower, pattern.lower()):
            return True
    return False


def _log_violation(host: Any, port: Any) -> None:
    """Schreibt Audit-Eintrag in system.db. Best-effort, niemals raise.

    Wenn das Logging scheitert, wird der Verstoss trotzdem geblockt
    (PermissionError wird vom Caller geworfen) — Audit ist nice-to-have,
    der Block ist hart.
    """
    if not _system_db_path:
        return
    try:
        stack = "".join(traceback.format_stack()[:-2])[-2000:]
        conn = sqlite3.connect(_system_db_path, timeout=2.0)
        try:
            conn.execute(
                "INSERT INTO agent_egress_violations "
                "(source, attempted_host, attempted_port, project_slug, "
                " pid, stack_summary) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    _source,
                    str(host) if host is not None else "<unknown>",
                    int(port) if (port is not None and isinstance(port, (int, str)) and str(port).isdigit()) else None,
                    _project_slug,
                    os.getpid(),
                    stack,
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        # Auditing darf niemals den Block verhindern. Stillschweigen.
        pass


def _block(host: Any, port: Any) -> "PermissionError":
    """Audit-Log + baut die PermissionError zum Werfen."""
    _log_violation(host, port)
    allowed_hint = ", ".join(_whitelist + sorted(_LOOPBACK_HOSTS)) or "(nur Loopback)"
    return PermissionError(
        f"Disco Network-Egress zu {host!r}:{port} geblockt. "
        f"Erlaubt: [{allowed_hint}]"
    )


def _patched_getaddrinfo(host, port, *args, **kwargs):
    """Hostname-Check vor DNS-Aufloesung. Caches resolved IPs."""
    if not _matches_whitelist(host):
        raise _block(host, port)
    result = _original_getaddrinfo(host, port, *args, **kwargs)
    # Cache resolved IPs so connect() can allow them by IP later.
    with _lock:
        for entry in result:
            sa = entry[4]
            if isinstance(sa, tuple) and len(sa) >= 1:
                _allowed_ips.add(sa[0])
    return result


def _patched_socket_connect(self, address):
    """Catch direct IP-Calls. Loopback OK, Cache-IP OK, sonst raise."""
    if isinstance(address, tuple) and len(address) >= 2:
        host = address[0]
        port = address[1]
        with _lock:
            ip_allowed = host in _allowed_ips
        if not (_is_loopback(host) or ip_allowed or _matches_whitelist(host)):
            raise _block(host, port)
    return _original_socket_connect(self, address)


def _patched_create_connection(address, *args, **kwargs):
    """Wie getaddrinfo, fuer den high-level Helper."""
    if isinstance(address, tuple) and len(address) >= 2:
        host = address[0]
        port = address[1]
        with _lock:
            ip_allowed = host in _allowed_ips
        if not (_is_loopback(host) or ip_allowed or _matches_whitelist(host)):
            raise _block(host, port)
    return _original_create_connection(address, *args, **kwargs)


def install_guard(
    whitelist: list[str] | None = None,
    source: str = "other",
    system_db_path: str | None = None,
    project_slug: str | None = None,
) -> None:
    """Aktiviert den Guard im aktuellen Process. Idempotent.

    Args:
        whitelist: Liste von fnmatch-Patterns (z.B. "*.openai.azure.com").
                   Loopback (127.0.0.0/8, ::1, localhost) ist IMMER erlaubt.
        source: Quelle des Subprocesses ('run_python', 'flow-runner', 'other').
        system_db_path: Absoluter Pfad zu system.db fuer Audit-Logging.
        project_slug: Optionaler Projekt-Slug-Kontext fuer Audit.
    """
    global _whitelist, _source, _system_db_path, _project_slug, _guard_installed

    _whitelist = list(whitelist or [])
    _source = source if source in ("run_python", "flow-runner", "other") else "other"
    _system_db_path = system_db_path
    _project_slug = project_slug

    if not _guard_installed:
        socket.getaddrinfo = _patched_getaddrinfo
        socket.socket.connect = _patched_socket_connect
        socket.create_connection = _patched_create_connection
        _guard_installed = True
