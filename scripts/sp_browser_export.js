/*
 * SharePoint-Browser-Export (rekursiv, ohne Graph-API, ohne App-Registrierung)
 * ---------------------------------------------------------------------------
 *
 * Einsatz:
 *   1. Im Browser auf der SharePoint-Seite einloggen (z.B. auf der Ziel-
 *      Bibliothek oder einem beliebigen Unterordner davon).
 *   2. DevTools öffnen (F12 / Cmd+Option+I) → Tab "Console".
 *   3. KONFIGURATION unten anpassen (siteUrl, startPath, outFile).
 *   4. Gesamten Inhalt dieser Datei in die Console kopieren, Enter drücken.
 *   5. Fortschritt wird pro Ordner ausgegeben. Am Ende lädt der Browser eine
 *      JSON-Datei herunter, die direkt von `bew sp import-json` verarbeitet
 *      werden kann.
 *
 * Warum dieser Umweg?
 *   Das einfache `/_api/.../Items?$filter=startswith(FileRef,'/path/')` fällt
 *   in SharePoint-Bibliotheken mit mehr als 5000 Items in den "List View
 *   Threshold" (HTTP 500/400). `GetFolderByServerRelativeUrl('<pfad>')` ist
 *   dagegen threshold-sicher und liefert pro Aufruf nur die direkten Kinder
 *   eines Ordners. Dieses Skript arbeitet die Ordnerstruktur rekursiv Level
 *   für Level ab und kombiniert die Ergebnisse.
 *
 * Das Skript:
 *   - fragt pro Ordner getrennt `Files` (Dateien) und `Folders` (Unterordner),
 *     jeweils mit `$expand=ListItemAllFields` → liefert alle Custom-Felder
 *     plus Metadaten direkt mit;
 *   - respektiert Pagination (`odata.nextLink`);
 *   - macht bei HTTP 429/503 automatisch Backoff-Retry;
 *   - gibt am Ende ein flaches Array aus, das sowohl Dateien als auch Ordner
 *     enthält (`FileSystemObjectType` 0 bzw. 1) — exakt das Format, das
 *     `SharePointJSONImporter` erwartet.
 */

(async () => {
  // ====== KONFIGURATION ======
  const siteUrl   = "https://vattenfall.sharepoint.com/sites/ReuterSiteDevelopment";
  const startPath = "/sites/ReuterSiteDevelopment/External Documents/Austauschordner_LagerhalleReuter/finale-Doku/Elektro";
  const outFile   = "elektro_export.json";
  // ===========================

  const esc   = s => s.replaceAll("'", "''");            // OData-Quote-Escape
  const path  = s => encodeURIComponent(esc(s));         // + URL-Encode
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const headers = { "Accept": "application/json;odata=nometadata" };

  async function fetchRetry(url, tries = 0) {
    const res = await fetch(url, { headers, credentials: "include" });
    if (res.status === 429 || res.status === 503) {
      if (tries >= 5) throw new Error("Zu oft gedrosselt");
      const w = parseInt(res.headers.get("Retry-After") || "2", 10) * 1000;
      console.warn(`Throttle ${res.status}, warte ${w}ms`);
      await sleep(w);
      return fetchRetry(url, tries + 1);
    }
    if (!res.ok) {
      const body = await res.text().catch(() => "");
      throw new Error(`HTTP ${res.status}: ${body.slice(0, 300)}`);
    }
    return res.json();
  }

  const items = [];           // flache Liste (Ordner + Dateien)
  const queue = [startPath];
  const seen  = new Set();
  const t0    = Date.now();

  while (queue.length) {
    const folder = queue.shift().replace(/\/$/, "");
    const key    = folder.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);

    let nFiles = 0, nDirs = 0;
    try {
      // --- Dateien in diesem Ordner ---
      let url = `${siteUrl}/_api/Web/GetFolderByServerRelativeUrl('${path(folder)}')`
              + `/Files?$expand=ListItemAllFields&$top=5000`;
      while (url) {
        const data = await fetchRetry(url);
        for (const f of data.value) {
          const li = f.ListItemAllFields || {};
          items.push({
            ...li,
            FileSystemObjectType: 0,
            FileLeafRef: li.FileLeafRef || f.Name,
            FileRef:     li.FileRef     || f.ServerRelativeUrl,
            File: {
              Length:           f.Length,
              TimeCreated:      f.TimeCreated,
              TimeLastModified: f.TimeLastModified,
            },
          });
          nFiles++;
        }
        url = data["odata.nextLink"] || null;
      }

      // --- Unterordner in diesem Ordner ---
      url = `${siteUrl}/_api/Web/GetFolderByServerRelativeUrl('${path(folder)}')`
          + `/Folders?$expand=ListItemAllFields&$top=5000`;
      while (url) {
        const data = await fetchRetry(url);
        for (const d of data.value) {
          // SharePoint legt in jeder Bibliothek einen Pseudo-Ordner "Forms"
          // mit Ansichts-Definitionen an — den überspringen wir.
          if (!d.ServerRelativeUrl || d.Name === "Forms") continue;
          const li = d.ListItemAllFields || {};
          items.push({
            ...li,
            FileSystemObjectType: 1,
            FileLeafRef: li.FileLeafRef || d.Name,
            FileRef:     li.FileRef     || d.ServerRelativeUrl,
          });
          queue.push(d.ServerRelativeUrl);
          nDirs++;
        }
        url = data["odata.nextLink"] || null;
      }
    } catch (e) {
      console.error(`FEHLER ${folder}: ${e.message}`);
      continue;
    }

    const short = folder.split("/").slice(-3).join("/");
    console.log(`[${seen.size}/${seen.size + queue.length}] ${short}  (${nFiles} Dateien, ${nDirs} Ordner)`);
    await sleep(80);  // höfliche Pause gegen Throttling
  }

  const dt = ((Date.now() - t0) / 1000).toFixed(1);
  console.log(`✓ Fertig: ${items.length} Items aus ${seen.size} Ordnern (${dt}s)`);

  const blob = new Blob([JSON.stringify(items, null, 2)], { type: "application/json" });
  const a = Object.assign(document.createElement("a"), {
    href: URL.createObjectURL(blob),
    download: outFile,
  });
  a.click();
  console.log(`⬇ Download: ${outFile}`);
})();
