"""Konvertiert einen SharePoint REST-API Atom-XML-Export in JSON.

Der SP REST-Endpunkt `_api/Web/Lists(guid'...')/Items` liefert per Default
Atom-XML (application/atom+xml). Der Importer `bew sp import-json` erwartet
aber JSON. Dieses Skript erzeugt ein JSON-Array aus dem XML, das direkt in
den Importer passt.

Aufruf:
    uv run python scripts/sp_xml_to_json.py <input.xml> <output.json>

Beispiel:
    uv run python scripts/sp_xml_to_json.py \\
        "Sharepoint Download/items.txt" \\
        data/sp_vattenfall_reuter.json

Design:
    - Streaming-Parsing mit iterparse → konstanter Speicher, auch bei 30+ MB
    - Nur `<m:properties>` innerhalb `<entry>` wird ausgewertet
    - `m:null="true"` → Feld wird weggelassen
    - `m:type="Edm.Int32"` → int, sonst String
    - Verschachtelte SP-Komplex-Typen (FieldUrlValue, etc.) werden übersprungen
    - Für jede Datei wird `File_x0020_Type` aus der Endung von FileLeafRef
      nachgetragen, damit der Importer die MIME-Type-Tabelle treffen kann
"""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# XML-Namespaces aus dem Atom-Feed
NS_ATOM = "http://www.w3.org/2005/Atom"
NS_D    = "http://schemas.microsoft.com/ado/2007/08/dataservices"
NS_M    = "http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"


def _local_name(tag: str) -> str:
    """Entfernt den {namespace}-Prefix aus einem Tag-Namen."""
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def _parse_value(elem: ET.Element) -> object | None:
    """Wandelt ein <d:FeldName>-Element in einen Python-Wert um.

    Rückgabe None bedeutet: Feld auslassen (NULL oder komplexer Typ).
    """
    # NULL
    if elem.get(f"{{{NS_M}}}null") == "true":
        return None

    edm_type = elem.get(f"{{{NS_M}}}type", "")

    # Komplexe Typen mit Kind-Elementen (z.B. SP.FieldUrlValue) → auslassen
    has_children = any(True for _ in elem)
    if has_children:
        return None

    text = (elem.text or "").strip()
    if not text:
        # Leerer String ist für SP REST oft gleichbedeutend mit NULL
        return None

    if edm_type == "Edm.Int32" or edm_type == "Edm.Int64":
        try:
            return int(text)
        except ValueError:
            return text
    if edm_type == "Edm.Double" or edm_type == "Edm.Decimal":
        try:
            return float(text)
        except ValueError:
            return text
    if edm_type == "Edm.Boolean":
        return text.lower() == "true"
    # Edm.DateTime, Edm.Guid, Strings usw. → as-is
    return text


def _derive_file_ext(leaf_ref: str) -> str | None:
    """Gibt die Dateiendung (ohne Punkt, lowercase) aus einem Dateinamen zurück."""
    if not leaf_ref or "." not in leaf_ref:
        return None
    ext = leaf_ref.rsplit(".", 1)[1].lower()
    # Endungen länger als ~10 Zeichen sind vermutlich kein Dateityp
    if len(ext) > 10 or not ext.isalnum():
        return None
    return ext


def convert(xml_path: Path, json_path: Path) -> int:
    """Streaming-Konvertierung. Rückgabe: Anzahl extrahierter Items."""
    properties_tag = f"{{{NS_M}}}properties"

    json_path.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    with json_path.open("w", encoding="utf-8") as out:
        out.write("[")
        first = True

        # iterparse mit ("start", "end"): wir werten erst bei "end" aus und
        # clearen anschließend den Knoten, damit der Speicher nicht wächst.
        context = ET.iterparse(str(xml_path), events=("end",))
        for _, elem in context:
            if elem.tag != properties_tag:
                continue

            item: dict[str, object] = {}
            for child in elem:
                name = _local_name(child.tag)
                value = _parse_value(child)
                if value is None:
                    continue
                item[name] = value

            # Datei-Typ aus der Endung ableiten (fehlt in diesem XML-Export)
            if item.get("FileSystemObjectType", 1) == 0:
                ext = _derive_file_ext(str(item.get("FileLeafRef") or ""))
                if ext and "File_x0020_Type" not in item:
                    item["File_x0020_Type"] = ext

            if not first:
                out.write(",")
            out.write("\n  ")
            json.dump(item, out, ensure_ascii=False)
            first = False
            total += 1

            # Speicher freigeben
            elem.clear()

        out.write("\n]\n")

    return total


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Aufruf: python sp_xml_to_json.py <input.xml> <output.json>", file=sys.stderr)
        return 2

    xml_path = Path(argv[1])
    json_path = Path(argv[2])

    if not xml_path.exists():
        print(f"Fehler: Eingabedatei nicht gefunden: {xml_path}", file=sys.stderr)
        return 1

    print(f"Konvertiere '{xml_path}' → '{json_path}' ...")
    count = convert(xml_path, json_path)
    size_kb = json_path.stat().st_size / 1024
    print(f"Fertig: {count} Items geschrieben ({size_kb:.0f} KB).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
