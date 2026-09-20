# Graph-RAG embedding builder

This package converts every canonical embedding input in
`corpus_catalog.json` into a deterministic NumPy matrix and JSONL row map for
loading into PostgreSQL with pgvector.

The pinned backend is FastEmbed 0.7.3 with `BAAI/bge-small-en-v1.5`. It emits
normalized 384-dimensional `float32` vectors for cosine search. The resolved
ONNX artifact and its SHA-256 are recorded in the build metadata.

## Install and prefetch

Use a dedicated Python 3.11 or 3.12 virtual environment:

```sh
python3 -m venv .venv
.venv/bin/pip install -r src/graphrag_runtime/requirements-local-embeddings.txt
.venv/bin/python src/graphrag_runtime/prefetch_model.py \
  --cache-dir runtime_data/GraphRAG/models/fastembed
```

Prefetch is the only command that requires network access. It fails if the
downloaded ONNX artifact does not match the pinned SHA-256.

## Build offline

```sh
HF_HUB_OFFLINE=1 .venv/bin/python src/graphrag_runtime/build_embeddings.py \
  --catalog runtime_data/GraphRAG/corpus_catalog.json \
  --project-root "$PWD" \
  --cache-dir runtime_data/GraphRAG/models/fastembed \
  --output-dir runtime_data/GraphRAG/embeddings \
  --batch-size 128 \
  --threads 4
```

Outputs are:

- `embeddings.npy`: `float32` matrix shaped `(record_count, 384)`;
- `embedding_rows.jsonl`: stable row-to-collection/record mapping;
- `embedding_progress.json`: batch-boundary resume checkpoint; and
- `embedding_manifest.json`: hashes, model provenance, shape, and pgvector
  contract.

After each batch, the matrix is flushed before the checkpoint advances. A
rerun resumes at the first uncommitted row and rejects changes to the catalog,
model, mapping, dimensions, or record count. Source file hashes and declared
record counts are validated before any embedding occurs.

Load `embedding_rows.jsonl` and the corresponding matrix rows into a pgvector
column declared as `vector(384)`. Use `vector_cosine_ops` and the `<=>`
operator. At this corpus size an exact scan is viable; add HNSW when measured
latency or concurrency calls for it.

Run the offline tests with:

```sh
PYTHONPATH=src/graphrag_runtime python3 -m unittest -v \
  src/graphrag_runtime/tests/test_build_embeddings.py
```
