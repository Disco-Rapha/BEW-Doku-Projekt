"""Wrapper, der das `_network_guard` aktiviert und dann das eigentliche
User-Script via `runpy.run_path` ausfuehrt.

Aufruf (typisch aus executor.py oder runner_host.py):

    python -m disco.agent._run_with_guard <user_script.py> [arg1 arg2 ...]

Die Whitelist + Kontext-Infos werden via ENV uebergeben (nicht via CLI-
Args, damit das User-Script saubere sys.argv sieht):

    DISCO_EGRESS_WHITELIST      "*.openai.azure.com,*.cognitiveservices.azure.com"
    DISCO_EGRESS_SOURCE         "run_python" | "flow-runner" | "other"
    DISCO_EGRESS_SYSTEM_DB      "/Users/BEW/Disco/system.db"
    DISCO_EGRESS_PROJECT_SLUG   "rea-denox"   (optional)

Wenn ENV-Variable fehlt oder leer, gilt: nur Loopback erlaubt
(_network_guard erlaubt 127.0.0.0/8, ::1, localhost immer).

Das User-Script laeuft danach mit `__name__ == "__main__"` und korrektem
`sys.argv = [<user_script>, *user_args]` — d.h. transparent.
"""

from __future__ import annotations

import os
import runpy
import sys


def main() -> int:
    if len(sys.argv) < 2:
        sys.stderr.write(
            "_run_with_guard: usage: python -m disco.agent._run_with_guard "
            "<script.py> [args...]\n"
        )
        return 2

    user_script = sys.argv[1]
    user_args = sys.argv[2:]

    # --- Guard aktivieren ---
    from disco.agent._network_guard import install_guard

    whitelist_raw = os.environ.get("DISCO_EGRESS_WHITELIST", "")
    whitelist = [p.strip() for p in whitelist_raw.split(",") if p.strip()]
    source = os.environ.get("DISCO_EGRESS_SOURCE", "other")
    system_db_path = os.environ.get("DISCO_EGRESS_SYSTEM_DB") or None
    project_slug = os.environ.get("DISCO_EGRESS_PROJECT_SLUG") or None

    install_guard(
        whitelist=whitelist,
        source=source,
        system_db_path=system_db_path,
        project_slug=project_slug,
    )

    # --- User-Script transparent ausfuehren ---
    # sys.argv so setzen dass das User-Script sich selbst als argv[0] sieht
    # und die User-Args ab argv[1].
    sys.argv = [user_script, *user_args]
    runpy.run_path(user_script, run_name="__main__")
    return 0


if __name__ == "__main__":
    sys.exit(main())
