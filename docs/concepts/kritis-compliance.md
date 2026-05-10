# ★ KRITIS-/Enterprise-Tauglichkeit: Disco-Box + BEW-Azure-Tenant

**Status:** Konzept, prio HOCH-strategisch nach BEW-Pitch.
**Entstanden:** 2026-05-10 (User-Disco-Diskussion).
**Notion-BL-Item:** verlinkt aus dem Disco-Backlog (Component: Compliance / Security).


**Stand:** strategisches Enabling-Setup fuer Disco-Einsatz bei
KRITIS-Kunden (Energie/Vattenfall). Diskussion 2026-05-10 zwischen
Raphael und Disco zur Vorbereitung der BEW-Pitch-Folge-Phase.

**Kerngedanke (zwei zusammenhaengende Konzepte):**

1. **Disco-Box als Vendor-Lab-Setup** statt BEW-Endpoint-Installation:
   Discoverse stellt einen eigenen Mac (M4 Pro, 32 GB / 1 TB, ~2.500 EUR
   einmalig) bei BEW physisch auf, der ausserhalb der Vattenfall-AAD/MDM-
   Domain laeuft. Sascha arbeitet daran wie an einem extern beigestellten
   Werkzeug. Umgeht 80 % der BEW-IT-Endpoint-Compliance (Code-Signatur-
   Standards, MECM/Intune-MDM, Conditional Access, SCCM-Pakete,
   SOC-Anbindung, Multi-User-Modell). Bleibt: AVV + TOM-Doku.

2. **BEW-eigener Azure-Tenant fuer LLM-Inferenz** statt Discoverse-
   Tenant: BEW richtet eigene Foundry-Endpoint + Document-Intelligence-
   Resource in Sweden Central ein. Disco-`.env` zeigt auf BEW-Endpoints.
   Daten verlassen Vattenfall *gar nicht mehr* — auch nicht fuer LLM-
   Calls. Discoverse wird vom Auftragsverarbeiter (DSGVO) zum Software-
   Lieferant. Pitch-Effekt: aus *„DSGVO-konform"* wird *„datensouveraen"*.

**Was Discoverse-/Disco-Code-seitig zu tun ist (ueberschaubar, ~1 Tag Code):**

- `.env`-Variablen sind schon konfigurierbar (`FOUNDRY_ENDPOINT`,
  `FOUNDRY_API_KEY`, `FOUNDRY_MODEL_DEPLOYMENT`, `FOUNDRY_AGENT_ID`).
- Auth-Pfad 3 (`DefaultAzureCredential` mit `az login`) sauber ausbauen
  — eleganter als API-Keys auf Disk in `.env`.
- `disco agent setup` muss in BEW-Tenant ein eigenes
  `disco-bew-prod-agent` pushen koennen.
- `docs/network-egress-policy.md` updaten: BEW-Endpoints statt
  Discoverse-Endpoints.

**Was BEW-Side zu tun ist (3–10 Werktage je nach Subscription-Stand):**

| Schritt | Was | Aufwand |
|---|---|---|
| 1 | Azure Subscription in Sweden Central freischalten (vermutlich vorhanden) | 0–Tage |
| 2 | Resource Group `rg-bew-disco-prod` anlegen | Min |
| 3 | Azure AI Foundry Project anlegen, Region Sweden Central | 1 h |
| 4 | Modell-Deployment GPT-5.x — Quota-Antrag bei Microsoft | 1–5 Tage |
| 5 | Document Intelligence Resource | 1 h |
| 6 | Service Principal / API-Keys fuer Disco | 1 h |
| 7 | Cost-Management + Budget-Alerts | 2 h |
| 8 | Disco `.env` umstellen + `agent setup` | 1 h (Discoverse) |

**Was zusaetzlich noch auf einer Disco-Box braucht (Phase A):**

- AVV + TOM-Anhang (1–2 Wochen vertraglich, kann parallel laufen)
- Geheimhaltungsvereinbarung
- Beistellungs-Vereinbarung (Hardware-Eigentum, Versicherung,
  Datenloeschung bei Vertragsende)
- TOM-Skelett (von Disco vorbereitet, ich pflege das vor dem ersten
  BEW-Compliance-Gespraech)

**Was damit ENTFAELLT vs. BEW-Endpoint-Pfad:**

- Code-Signatur Apple-Notarization-BEW-IT-Standard (Discoverse-Standard
  reicht)
- MECM/Intune-MDM-Compliance
- Conditional Access Policy fuer Disco-App
- Vattenfall-AAD-App-Registration (in Phase A)
- BEW-IT-Approval-Prozess fuer jede Software-Aenderung
- BEW-IT-Standard Patch-Management (Discoverse-managed, dokumentiert
  im TOM)
- SOC-Anbindung an Vattenfall-SIEM (in Phase A)
- Multi-User mit Rollen (in Phase A — Single-User-Box passt)

**Realistischer Roadmap-Vorschlag (drei Phasen):**

- **Phase A — Disco-Box live + AVV + TOM:** 4–6 Wochen
  - Hardware beschaffen
  - AVV-Entwurf an BEW-Compliance
  - Disco produktiv aufsetzen, OneDrive-Sync auf Box
  - Sascha bekommt Zugriff; Live-Betrieb startet
- **Phase B — BEW-eigener Azure-Tenant:** 1–2 Wochen nach Phase A
  - BEW richtet ihre Azure-Seite ein (Schritte 1–7 oben)
  - Disco-Code Auth-Politur
  - Cut-Over an Tag X (vorher 100 % Discoverse, nachher 100 % BEW)
- **Phase C — App-Registration + API-Sync (~6–12 Monate spaeter):**
  - Wenn Volumen waechst: Microsoft-Graph-API mit `Sites.Selected`
  - SSO/Multi-User/SOC-Anbindung
  - SharePoint-Sync zurueck im Code (alter Connector aus Commit
    351798e als Ausgangsbasis)

**Wichtig fuer Pitch-Briefing:**

Section 9 (*Stack-Highlights fuer Compliance-Fragen*) und Section 12
(*Wenn-Sven-fragt-X*) sollten erweitert werden um:

- *„Multi-Tenant-Modus"* als Compliance-Highlight: *„Ihre Daten gehen
  ueber EUREN Azure-Tenant, nicht ueber meinen."*
- *„Wenn Sven fragt: wer sieht unsere Daten in der Cloud?"* mit klarer
  Drei-Phasen-Antwort: heute (Discoverse-Tenant), Phase A (gleich,
  Disco-Box), Phase B (BEW-Tenant, Discoverse hat technisch keinen
  Zugriff mehr).

**Vorbereitung nach BEW-Pitch (wenn gruenes Licht):**

1. BEW-Azure-Setup-Runbook fuer BEW-IT (Schritt-fuer-Schritt
   Azure-Portal-UI)
2. Cost-Forecast fuer BEW-Side (gleiche Tarife, direkt bezahlt)
3. Disco-Code-Updates (Auth-Pfad-Politur, Multi-Tenant-`.env`)
4. Pitch-Briefing-Update um die zwei neuen Argumente
5. TOM-Skelett fuer den AVV mit BEW
6. Disco-Box-Setup-Runbook als Operations-Doc

**Knackpunkte:**

- Modell-Verfuegbarkeit pruefen (GPT-5.x in Sweden Central — wir
  nutzen es schon, sollte gehen)
- Quota-Bestellung — neue Subscriptions haben anfangs niedrige Quotas
- Foundry-Tarife je nach Microsoft-Vereinbarung anders
  (Enterprise-Preis vs PAYG)
- Cost-Controlling — BEW muss Budget-Alerts setzen
- Cut-Over-Datum klar definieren (wer zahlt was ab wann)

**Anschluss an bestehende Bausteine:**

- Disco ist heute schon konfigurierbar (alle Foundry-Vars in `.env`)
- Egress-Policy ist verbindlich dokumentiert (`docs/network-egress-policy.md`)
- Workspace-Trennung Code/Daten ist Architektur-Regel
- Lock-in-Vermeidung war Architektur-Prinzip von Anfang an (SQLite +
  Markdown + Excel als portable Daten-Architektur)

**Wann starten:** sobald Sven am 2026-05-12 gruenes Licht gibt fuer
weitere RSD-Phasen mit Disco. Vorher: AVV + TOM vorbereiten, Hardware
sondieren, BEW-Compliance-Kontaktpfad finden.
