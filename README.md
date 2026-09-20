# RCA/COSZO Graph-RAG

This repository contains the reproducible RCA/COSZO corpus pipelines,
PostgreSQL/pgvector Graph-RAG runtime, public API, and live agent tools.

The large corpus, source archive, embeddings, operational snapshots, and
provenance files are versioned as private GitHub Release assets. They are kept
out of ordinary Git history so a clone stays small and generated databases do
not accumulate full binary copies on every update.

## Restore on a new machine

Install Git, GitHub CLI, Docker, and `zstd`, authenticate GitHub CLI, then run:

```sh
git clone https://github.com/coszo-hub/RCA-Atlas.git
cd RCA-Atlas
./scripts/bootstrap_machine.sh --release latest
cd src/graphrag_runtime
docker compose up -d db
docker compose --profile load run --rm loader
docker compose up -d api
```

The bootstrap command downloads the release manifest and three versioned
archives, verifies every SHA-256 digest, and restores their original paths.
See `src/DATA_CORPUS_METHOD.md` for the complete collection and tool method.

## Create a transfer release

From a complete project checkout:

```sh
./scripts/build_transfer_release.sh
gh release create corpus-YYYYMMDD transfer_dist/* \
  --title "RCA/COSZO corpus YYYY-MM-DD" \
  --notes "Versioned corpus, sources, runtime index, and embeddings."
```

Release archives contain data only. Credentials, local virtual environments,
Python caches, and macOS metadata are excluded.

## License

RCA Atlas software and original documentation are proprietary and all rights
are reserved. Reuse requires prior written permission; see `LICENSE`. External
data, publications, figures, website content, and vendored components retain
their source-specific rights and licenses; see `THIRD_PARTY_NOTICES.md`.
