# Operations Runbook — Disco

Spickzettel für die wiederkehrenden Aufgaben rund um Dev-/Prod-Betrieb,
Deploys, Foundry-Push, Rollback. Kein vollständiges Handbuch — die
ausführliche Begründung steht in `CLAUDE.md` Section *Entwicklungs-
Pipeline*.

**Stand:** 2026-05-09.

---

## Topologie

| Komponente | Pfad | Port | Workspace |
|---|---|---|---|
| Dev-Worktree | `~/Claude/BEW Doku Projekt/` (Branch `dev`) | `:8766` | `~/Disco-dev` |
| Prod-Worktree | `~/Claude/BEW Doku Prod/` (Branch `main`) | `:8765` | `~/Disco` |
| Foundry-Agent dev | `disco-dev-agent` (Sweden Central) | — | — |
| Foundry-Agent prod | `disco-prod-agent` (Sweden Central) | — | — |

Beide Worktrees teilen das gleiche `.git/`. Refs (`dev`, `main`) sind
in beiden sichtbar, sobald lokal aktualisiert.

---

## Dev-Server starten

```bash
cd "/Users/BEW/Claude/BEW Doku Projekt" && \
  DISCO_WORKSPACE=~/Disco-dev \
  uv run uvicorn disco.api.main:app --host 127.0.0.1 --port 8766 --reload
```

`--reload` greift bei Code-Änderungen automatisch (Skills brauchen
keinen Reload, werden live von Disk geladen).

## Prod-Server starten

```bash
cd "/Users/BEW/Claude/BEW Doku Prod" && \
  DISCO_WORKSPACE=~/Disco \
  uv run uvicorn disco.api.main:app --host 127.0.0.1 --port 8765 --reload
```

---

## Standard-Deploy (dev → prod, mit Bestätigung)

**1. Auf dev fertigstellen + committen:**

```bash
cd "/Users/BEW/Claude/BEW Doku Projekt"
git status
git add <files>
git commit -m "..."
```

**2. Im Chat fragen** — *„Soll ich auf Prod ziehen?"* — und Antwort
abwarten.

**3. Nach Freigabe: ff-merge im Prod-Worktree:**

```bash
cd "/Users/BEW/Claude/BEW Doku Prod" && git merge --ff-only dev
```

`--ff-only` garantiert lineare History. Bei Divergenz bricht der Merge
ab — dann Rückfrage statt Force-Merge.

**4. Wenn System-Prompt oder Tool-Schemas geändert wurden:**

```bash
cd "/Users/BEW/Claude/BEW Doku Prod" && \
  DISCO_WORKSPACE=~/Disco uv run disco agent setup
```

Pusht `system_prompt.md` + Tool-Schemas zum Foundry-Portal-Agent.
Erzeugt eine neue Version (z. B. `disco-prod-agent v51`), Rollback
über Portal möglich.

**Nicht nötig wenn nur Skills oder Frontend geändert wurden** —
Skills laden live von Disk, Frontend läuft über `--reload`.

**5. Verifikation:**

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8765/
curl -s "http://127.0.0.1:8765/openapi.json" | python3 -c "import sys,json; print(len(json.load(sys.stdin)['paths']))"
```

---

## Rollback

**Code-Rollback (Prod-Worktree zurück auf vorherigen Stand):**

```bash
cd "/Users/BEW/Claude/BEW Doku Prod"
git log --oneline -5                  # vorherigen Hash finden
git reset --hard <commit-hash>
```

`git reflog` zeigt alle Stände der letzten Tage — nichts geht verloren.

**Foundry-Agent-Rollback:** im Portal `disco-prod-agent` öffnen,
ältere Version auswählen, „Activate". Nach Auswahl wirken alte
System-Prompt + Tool-Schemas sofort.

**DISCO.md-Rollback (pro Projekt):** alle Migrationen am 2026-05-09
haben einen Backup hinterlassen:

```bash
cp ~/Disco/projects/<slug>/DISCO.md.backup-2026-05-09 \
   ~/Disco/projects/<slug>/DISCO.md
```

---

## Server-Neustart

Wenn `--reload` mal hängt oder ein Foundry-Agent-Switch live werden
soll:

```bash
# PID finden
lsof -i :8765 -sTCP:LISTEN
# oder :8766 für dev
# Eltern-PID killen (Worker beenden sich mit)
kill <pid>
# Server neu starten (siehe oben)
```

---

## Häufige Checks

```bash
# Foundry-Agent-Versionen einsehen (Foundry Portal)
# https://ai.azure.com → Sweden-central-deployment → Agents

# Tool-Count prüfen
cd "/Users/BEW/Claude/BEW Doku Projekt" && \
  uv run python -c "from disco.agent.functions import FUNCTIONS; print(len(FUNCTIONS))"

# Migrations-Stand pro Projekt
disco db status --project <slug>

# Memory-Trace eines Projekts
cat ~/Disco/projects/<slug>/.disco/memory-access.log
```

---

## GitHub-Backup (User, nicht-blockierend)

Push beider Branches via GitHub Desktop, **wenn es passt**. Nicht für
den Deploy nötig — `origin` ist Backup, nicht Gate. Nach
`--ff-only`-Deploys bleibt die History linear, normaler Push reicht.

Falls `origin/main` nach einem PR-Merge divergiert ist, einmalig
**Force-Push** (`git push --force-with-lease origin main`) zur
Bereinigung; danach wieder normal.

---

## Sicherheits-Checkliste vor Demo / Customer-Sitzung

- [ ] Prod-Server läuft auf `:8765`, antwortet `200`
- [ ] Foundry-Agent-Version aktuell (`disco-prod-agent` neueste Version)
- [ ] DISCO.md aller drei Prod-Projekte hat den Marker
      `<!-- DISCO-LAYER-1-END -->`
- [ ] HTML-Viewer funktioniert (Test mit `exports/*.html` in einem
      Projekt)
- [ ] `agent_table_docs` ist befüllt für die Tabellen, die in der Demo
      angesprochen werden (sonst Trockene `table_doc_get`-Antworten)
- [ ] Backup-Kopien `DISCO.md.backup-YYYY-MM-DD` existieren neben
      jedem migrierten DISCO.md
- [ ] `git status` in beiden Worktrees clean
