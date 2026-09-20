# PostgreSQL Graph-RAG runtime

This package normalizes the 13 RCA/COSZO collections into an immutable build,
loads it into PostgreSQL 16 with pgvector, and exposes bounded hybrid retrieval,
graph traversal, and tool-routing functions through a small authenticated API.

## Build and load

Run the normalizer against the project that owns `runtime_data/GraphRAG/corpus_catalog.json`:

```sh
python normalize_corpus.py --project-root /path/to/project --output /path/to/normalized
```

The normalizer verifies every catalogued input's byte size, SHA-256, JSONL row
count, node identity, edge endpoint, and chunk link before publishing the output
directory. It retains every physical node and edge row while also producing the
collection-scoped logical nodes and unique edge facts used at query time.

Apply `migrations/001_initial.sql` with a dedicated owner/migration role. The
`002_local_api_role.sql` migration is only for local Compose development; use a
secret manager and infrastructure-managed role in production. Generate the
384-dimensional BGE embedding artifact, then load and activate it:

```sh
python src/graphrag_runtime/prefetch_model.py \
  --cache-dir runtime_data/GraphRAG/models/fastembed
HF_HUB_OFFLINE=1 python src/graphrag_runtime/build_embeddings.py \
  --catalog runtime_data/GraphRAG/corpus_catalog.json \
  --project-root "$PWD" \
  --cache-dir runtime_data/GraphRAG/models/fastembed \
  --output-dir runtime_data/GraphRAG/embeddings
python load_postgres.py --dsn "$OWNER_DATABASE_URL" --normalized /path/to/normalized \
  --embeddings /path/to/embeddings --activate
```

Loading is transactional and serialized. Activation calls
`graphrag.activate_build`, which refuses unvalidated builds and atomically flips
the single active-build pointer under an advisory lock. Existing active readers
continue on a consistent MVCC snapshot.

## Public isolation

The service database role has no access to `graphrag` tables. It can execute
only the four bounded `graphrag_api` functions. The database should remain on
a private network behind the API, with TLS, proxy-level request rate limits,
secret rotation, and connection limits. The API accepts neither SQL nor raw
`tsquery` fragments. Functions cap result counts, collection filters, graph
depth, predicate filters, and execution time.

The checked-in Compose credentials are development-only. Bindings expose the
API only on loopback and do not expose PostgreSQL on the host.

## Verification

Run local static and API tests with:

```sh
python -m unittest discover -s tests -v
python -m py_compile normalize_corpus.py load_postgres.py app/*.py tests/*.py
docker compose config --quiet
```

A production release should additionally apply both migrations to an empty
PostgreSQL/pgvector database, load the normalized corpus and embeddings, verify
the manifest counts, and exercise each API function using only the restricted
service role.
