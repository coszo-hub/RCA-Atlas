# Figures and datasheets Graph-RAG pipelines

This source directory contains reproducible builders for the curated image and technical-document folders.

- `build_figures_graph.py` adds verified descriptions, OCR labels, graph entities, site/infrastructure links, version-family links, and cross-corpus image matches without copying or changing the source images.
- `build_datasheets_graph.py` extracts native page text, renders every PDF page, OCRs sparse and schematic pages, creates page-bounded chunks and visual records, and links documents to products, software, standards, and the existing instrument inventory.

Generated packages belong in `data/Figures/graphrag` and `data/Datasheets/graphrag`. Source files remain in their parent folders.

Requirements: Python 3 with `pypdf` and Pillow, Poppler (`pdftoppm`, `pdfimages`), and Tesseract OCR.
