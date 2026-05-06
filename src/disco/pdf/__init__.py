"""PDF-Pipeline-Kern: Markdown-Extraktion und Engine-Dispatcher.

Zwei produktive Engines, gewaehlt durch den vorgelagerten Routing-Flow
(extraction_routing_decision):

  - azure-di          — Azure Document Intelligence prebuilt-layout.
                         Default fuer Standard-PDFs.
  - azure-di-hr       — Azure DI prebuilt-layout + ocrHighResolution.
                         Fuer vdrawing/Plan-Format/grosse Bildflaechen
                         (feine Schriften in Plantitelblocks).
"""

from .markdown import ENGINES, EXTRACTOR_VERSION, extract_markdown

__all__ = ["ENGINES", "EXTRACTOR_VERSION", "extract_markdown"]
