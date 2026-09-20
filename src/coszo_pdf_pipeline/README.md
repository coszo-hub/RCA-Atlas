# COSZO PDF Graph RAG pipeline

`build_coszo_pdf_graph.py` converts the PDF files in `data/coszo` into a provenance-preserving Graph RAG package. It extracts native text, OCRs scans and visual pages with Tesseract, renders every page, creates page-bounded chunks, links named entities and instrument records, keeps duplicate content, and emits validation results.

Requirements: Python 3 with `pypdf` and Pillow, Poppler (`pdftoppm`), and Tesseract OCR.

Example:

```bash
python build_coszo_pdf_graph.py \
  --source-dir "/path/to/data/coszo" \
  --output-dir "/path/to/data/coszo/graphrag" \
  --instrument-records "/path/to/data/Instruments/instruments.jsonl" \
  --overwrite
```

The generated data belongs under `data/coszo/graphrag`; keep this source code under `src/coszo_pdf_pipeline`.
