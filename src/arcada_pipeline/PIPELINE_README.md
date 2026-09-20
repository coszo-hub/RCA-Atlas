# Arcada Graph-RAG pipeline

Source repository: `https://github.com/mhemmett/arcada/` at commit `14294bca45ce5f65fd6541bea68ab40fbc870659`.

`build_arcada_graph.py` converts Arcada's built `public/chunks.json` into the runtime corpus under `../../data/Arcada`.

The conversion:

- retains Arcada's instrument, paper, site-context, and data-access content;
- retains all 802 source rows and repairs six placeholder-only duplicate PI rows with unique graph IDs and an audit trail;
- namespaces all document and chunk IDs;
- groups overlapping paper chunks under stable parent documents;
- emits shared RCA/COSZO site entities compatible with the Literature and Websites graphs;
- preserves DOIs, source URLs, linked instrument identifiers, repository revision, and raw-text hashes;
- creates placeholder reference nodes for linked instruments absent from Arcada's source chunks;
- validates every graph endpoint and every document/chunk chain.

The source snapshot contains `public/chunks.json`, the native embeddings, MiniSearch index and embedding hashes, the source catalogs used to enrich the graph, the repository README, and LICENSE. Native retrieval artifacts remain available for provenance but are not mixed into the Graph-RAG runtime because its IDs and normalized text differ.

Arcada's repository is MIT licensed, but extracted paper text and scraped third-party pages retain their original rights. The corpus does not label third-party content as MIT.
