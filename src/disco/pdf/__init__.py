"""PDF-Pipeline-Kern: Markdown-Extraktion und Engine-Dispatcher.

Drei produktive Engines, gewaehlt durch den vorgelagerten Routing-Flow
(pdf_routing_decision):

  - docling-standard  — DocLayNet + TableFormer ACCURATE + EasyOCR (MPS).
                         Default fuer Text-PDFs mit strukturierten Tabellen.
  - azure-di          — Azure Document Intelligence prebuilt-layout.
                         Fuer Scan-PDFs (hohe OCR-Qualitaet).
  - azure-di-hr       — Azure DI prebuilt-layout + ocrHighResolution.
                         Fuer vdrawing/Plan-Format/grosse Bildflaechen
                         (feine Schriften in Plantitelblocks).
"""

from .markdown import ENGINES, EXTRACTOR_VERSION, extract_markdown

__all__ = ["ENGINES", "EXTRACTOR_VERSION", "extract_markdown"]
