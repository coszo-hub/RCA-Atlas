# Microsoft GraphRAG candidate layer

This optional layer applies Microsoft GraphRAG only to unstructured Atlas
documents. It writes **candidate** entities, relationships, communities, and
reports; it never writes into the authoritative PostgreSQL graph directly.

Every exported input document carries its Atlas chunk ID, collection ID, source
URL, and content hash. Candidate edges must retain those references and pass
evaluation/review before a separately approved merge.

## Prepare a pilot

```bash
python3 src/microsoft_graphrag_layer/prepare_input.py \
  --chunks runtime_data/GraphRAG/normalized/chunks.jsonl \
  --output /tmp/atlas-ms-graphrag-pilot \
  --collections literature websites figures_datasheets --limit 100
```

Install and initialize a pinned Microsoft GraphRAG release in the pilot output,
then copy `settings.template.yaml` to its `settings.yaml`. Set
`GRAPHRAG_API_KEY` only in that pilot's ignored `.env`. Run indexing there,
evaluate candidate edges against Atlas gold questions, and retain the output as
a versioned external artifact rather than committing it.

The template deliberately uses a separate `GRAPHRAG_API_KEY`; Gemini and Atlas
runtime secrets are not reused implicitly.
