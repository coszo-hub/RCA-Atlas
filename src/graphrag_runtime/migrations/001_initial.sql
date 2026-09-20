BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS graphrag;
CREATE SCHEMA IF NOT EXISTS graphrag_api;
-- SECURITY DEFINER functions resolve pgvector operators from public. Make that
-- schema non-writable to untrusted roles before any API function can execute.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

CREATE TABLE graphrag.corpus_builds (
    build_id text PRIMARY KEY CHECK (build_id ~ '^[0-9a-f]{64}$'),
    catalog_fingerprint_sha256 text NOT NULL UNIQUE CHECK (catalog_fingerprint_sha256 ~ '^[0-9a-f]{64}$'),
    schema_version text NOT NULL,
    created_at_utc timestamptz NOT NULL,
    manifest jsonb NOT NULL,
    validation_passed boolean NOT NULL DEFAULT false
);

CREATE TABLE graphrag.active_corpus (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    build_id text NOT NULL REFERENCES graphrag.corpus_builds(build_id)
);

CREATE TABLE graphrag.collections (
    build_id text NOT NULL REFERENCES graphrag.corpus_builds(build_id) ON DELETE CASCADE,
    collection_id text NOT NULL,
    name text NOT NULL,
    root_path text NOT NULL,
    scope text,
    manifest jsonb NOT NULL,
    PRIMARY KEY (build_id, collection_id)
);

CREATE TABLE graphrag.source_files (
    source_file_pk bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    build_id text NOT NULL,
    file_id text NOT NULL,
    collection_id text NOT NULL,
    relative_path text NOT NULL,
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    byte_size bigint NOT NULL CHECK (byte_size >= 0),
    record_count bigint CHECK (record_count IS NULL OR record_count >= 0),
    UNIQUE (build_id, file_id),
    FOREIGN KEY (build_id, collection_id) REFERENCES graphrag.collections(build_id, collection_id) ON DELETE CASCADE
);

CREATE TABLE graphrag.source_file_roles (
    source_file_pk bigint NOT NULL REFERENCES graphrag.source_files(source_file_pk) ON DELETE CASCADE,
    role text NOT NULL CHECK (role IN ('embedding', 'graph_node', 'graph_edge', 'structured', 'auxiliary', 'tool')),
    PRIMARY KEY (source_file_pk, role)
);

CREATE TABLE graphrag.nodes (
    node_pk bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    build_id text NOT NULL,
    collection_id text NOT NULL,
    local_id text NOT NULL CHECK (local_id <> ''),
    display_name text NOT NULL,
    summary text,
    source_url text,
    record_kinds text[] NOT NULL,
    representative_payload jsonb NOT NULL,
    UNIQUE (build_id, collection_id, local_id),
    FOREIGN KEY (build_id, collection_id) REFERENCES graphrag.collections(build_id, collection_id) ON DELETE CASCADE
);

CREATE TABLE graphrag.node_records (
    node_record_pk bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_file_pk bigint NOT NULL REFERENCES graphrag.source_files(source_file_pk) ON DELETE CASCADE,
    line_no integer NOT NULL CHECK (line_no > 0),
    node_pk bigint NOT NULL REFERENCES graphrag.nodes(node_pk) ON DELETE CASCADE,
    record_kind text NOT NULL,
    payload_sha256 text NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    source_is_untrusted_data boolean NOT NULL DEFAULT true,
    payload jsonb NOT NULL,
    UNIQUE (source_file_pk, line_no)
);

CREATE TABLE graphrag.node_identifiers (
    node_pk bigint NOT NULL REFERENCES graphrag.nodes(node_pk) ON DELETE CASCADE,
    identifier text NOT NULL,
    identifier_type text NOT NULL,
    PRIMARY KEY (node_pk, identifier, identifier_type)
);

CREATE INDEX node_identifiers_lookup ON graphrag.node_identifiers (lower(identifier));

CREATE TABLE graphrag.chunks (
    chunk_pk bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    build_id text NOT NULL,
    collection_id text NOT NULL,
    chunk_id text NOT NULL,
    node_pk bigint NOT NULL UNIQUE REFERENCES graphrag.nodes(node_pk) ON DELETE CASCADE,
    title text NOT NULL,
    section_heading text,
    body text NOT NULL CHECK (length(btrim(body)) > 0),
    source_url text,
    locator text,
    text_sha256 text NOT NULL CHECK (text_sha256 ~ '^[0-9a-f]{64}$'),
    metadata jsonb NOT NULL,
    search_tsv tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(section_heading, '')), 'B') ||
        setweight(to_tsvector('english', coalesce(body, '')), 'C')
    ) STORED,
    UNIQUE (build_id, collection_id, chunk_id),
    FOREIGN KEY (build_id, collection_id) REFERENCES graphrag.collections(build_id, collection_id) ON DELETE CASCADE
);

CREATE INDEX chunks_search_gin ON graphrag.chunks USING gin (search_tsv);

CREATE TABLE graphrag.chunk_links (
    chunk_pk bigint NOT NULL REFERENCES graphrag.chunks(chunk_pk) ON DELETE CASCADE,
    link_type text NOT NULL CHECK (link_type IN ('DOCUMENT', 'PARENT', 'PAGE', 'SOURCE', 'ENTITY')),
    target_node_pk bigint NOT NULL REFERENCES graphrag.nodes(node_pk) ON DELETE CASCADE,
    PRIMARY KEY (chunk_pk, link_type, target_node_pk)
);

CREATE TABLE graphrag.edge_records (
    edge_record_pk bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_file_pk bigint NOT NULL REFERENCES graphrag.source_files(source_file_pk) ON DELETE CASCADE,
    line_no integer NOT NULL CHECK (line_no > 0),
    raw_edge_id text,
    source_node_pk bigint NOT NULL REFERENCES graphrag.nodes(node_pk) ON DELETE CASCADE,
    predicate text NOT NULL CHECK (predicate <> ''),
    target_node_pk bigint NOT NULL REFERENCES graphrag.nodes(node_pk) ON DELETE CASCADE,
    payload_sha256 text NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL,
    UNIQUE (source_file_pk, line_no)
);

CREATE TABLE graphrag.edge_facts (
    edge_fact_pk bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    build_id text NOT NULL REFERENCES graphrag.corpus_builds(build_id) ON DELETE CASCADE,
    collection_id text NOT NULL,
    source_node_pk bigint NOT NULL REFERENCES graphrag.nodes(node_pk) ON DELETE CASCADE,
    predicate text NOT NULL CHECK (predicate <> ''),
    target_node_pk bigint NOT NULL REFERENCES graphrag.nodes(node_pk) ON DELETE CASCADE,
    UNIQUE (build_id, collection_id, source_node_pk, predicate, target_node_pk),
    FOREIGN KEY (build_id, collection_id) REFERENCES graphrag.collections(build_id, collection_id) ON DELETE CASCADE
);

CREATE INDEX edge_facts_source ON graphrag.edge_facts (build_id, source_node_pk);
CREATE INDEX edge_facts_target ON graphrag.edge_facts (build_id, target_node_pk);
CREATE INDEX edge_facts_predicate ON graphrag.edge_facts (build_id, predicate);

CREATE TABLE graphrag.structured_records (
    structured_record_pk bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_file_pk bigint NOT NULL REFERENCES graphrag.source_files(source_file_pk) ON DELETE CASCADE,
    line_no integer NOT NULL CHECK (line_no > 0),
    collection_id text NOT NULL,
    record_id text NOT NULL CHECK (record_id <> ''),
    subject_id text,
    observed_at text,
    payload jsonb NOT NULL,
    UNIQUE (source_file_pk, line_no)
);

CREATE INDEX structured_subject ON graphrag.structured_records (collection_id, subject_id);
CREATE INDEX structured_payload_gin ON graphrag.structured_records USING gin (payload jsonb_path_ops);

CREATE TABLE graphrag.tools (
    tool_pk bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    build_id text NOT NULL,
    collection_id text NOT NULL,
    name text NOT NULL CHECK (name <> ''),
    description text NOT NULL,
    input_schema jsonb NOT NULL,
    runtime text,
    manifest_path text NOT NULL,
    metadata jsonb NOT NULL,
    search_tsv tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('simple', replace(name, '_', ' ')), 'A') ||
        setweight(to_tsvector('english', coalesce(description, '')), 'B')
    ) STORED,
    UNIQUE (build_id, collection_id, name),
    FOREIGN KEY (build_id, collection_id) REFERENCES graphrag.collections(build_id, collection_id) ON DELETE CASCADE
);

CREATE INDEX tools_search_gin ON graphrag.tools USING gin (search_tsv);

CREATE TABLE graphrag.embeddings (
    chunk_pk bigint NOT NULL REFERENCES graphrag.chunks(chunk_pk) ON DELETE CASCADE,
    model_id text NOT NULL,
    model_revision text NOT NULL,
    model_artifact_sha256 text,
    dimensions integer NOT NULL CHECK (dimensions = 384),
    normalized boolean NOT NULL,
    text_sha256 text NOT NULL CHECK (text_sha256 ~ '^[0-9a-f]{64}$'),
    embedding vector(384) NOT NULL,
    PRIMARY KEY (chunk_pk, model_id)
);

CREATE INDEX embeddings_hnsw_cosine ON graphrag.embeddings USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE OR REPLACE FUNCTION graphrag_api.runtime_health()
RETURNS TABLE (ready boolean, build_id text, chunk_count bigint, embedding_count bigint)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, graphrag
SET statement_timeout = '2s'
AS $$
WITH active AS (SELECT build_id FROM graphrag.active_corpus WHERE singleton),
counts AS (
    SELECT a.build_id,
           (SELECT count(*) FROM graphrag.chunks c WHERE c.build_id=a.build_id) AS chunk_count,
           (SELECT count(*) FROM graphrag.embeddings e JOIN graphrag.chunks c USING(chunk_pk) WHERE c.build_id=a.build_id) AS embedding_count
    FROM active a
)
SELECT chunk_count > 0 AND embedding_count = chunk_count, build_id, chunk_count, embedding_count FROM counts
$$;

CREATE OR REPLACE FUNCTION graphrag.activate_build(candidate_build_id text)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, graphrag
AS $$
DECLARE
    candidate_valid boolean;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtext('graphrag_active_build'));
    SELECT validation_passed INTO candidate_valid
    FROM graphrag.corpus_builds
    WHERE build_id = candidate_build_id
    FOR UPDATE;
    IF candidate_valid IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'build % is missing or has not passed validation', candidate_build_id;
    END IF;
    INSERT INTO graphrag.active_corpus(singleton, build_id)
    VALUES (true, candidate_build_id)
    ON CONFLICT (singleton) DO UPDATE SET build_id = excluded.build_id;
END
$$;

CREATE OR REPLACE FUNCTION graphrag_api.hybrid_search(
    query_text text,
    query_embedding vector(384),
    result_limit integer DEFAULT 12,
    collection_filter text[] DEFAULT NULL,
    model_filter text DEFAULT 'BAAI/bge-small-en-v1.5',
    lexical_weight double precision DEFAULT 0.45,
    vector_weight double precision DEFAULT 0.55
) RETURNS TABLE (
    chunk_pk bigint, collection_id text, chunk_id text, node_local_id text,
    title text, body text, source_url text, locator text,
    citation_source_id text, citation_title text, citation_url text,
    score double precision, vector_rank bigint, lexical_rank bigint
) LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, graphrag, public
SET statement_timeout = '5s'
SET hnsw.iterative_scan = 'strict_order'
AS $$
WITH active AS (
    SELECT build_id FROM graphrag.active_corpus WHERE singleton
), bounded AS (
    SELECT greatest(1, least(coalesce(result_limit, 12), 50)) AS n
), vector_hits AS (
    SELECT c.chunk_pk, row_number() OVER (ORDER BY e.embedding <=> query_embedding) AS rank
    FROM graphrag.embeddings e
    JOIN graphrag.chunks c USING (chunk_pk)
    JOIN active a USING (build_id), bounded b
    WHERE e.model_id = coalesce(model_filter, 'BAAI/bge-small-en-v1.5')
      AND (collection_filter IS NULL OR c.collection_id = ANY(collection_filter[1:20]))
    ORDER BY e.embedding <=> query_embedding
    LIMIT (SELECT n * 4 FROM bounded)
), lexical_hits AS (
    SELECT c.chunk_pk,
           row_number() OVER (ORDER BY ts_rank_cd(c.search_tsv, websearch_to_tsquery('english', left(coalesce(query_text, ''), 1000))) DESC) AS rank
    FROM graphrag.chunks c
    JOIN active a USING (build_id), bounded b
    WHERE c.search_tsv @@ websearch_to_tsquery('english', left(coalesce(query_text, ''), 1000))
      AND (collection_filter IS NULL OR c.collection_id = ANY(collection_filter[1:20]))
    ORDER BY ts_rank_cd(c.search_tsv, websearch_to_tsquery('english', left(coalesce(query_text, ''), 1000))) DESC
    LIMIT (SELECT n * 4 FROM bounded)
), fused AS (
    SELECT coalesce(v.chunk_pk, l.chunk_pk) AS chunk_pk,
           v.rank AS vector_rank, l.rank AS lexical_rank,
           greatest(0.0, least(coalesce(vector_weight, 0.55), 1.0)) * coalesce(1.0 / (60 + v.rank), 0)
           + greatest(0.0, least(coalesce(lexical_weight, 0.45), 1.0)) * coalesce(1.0 / (60 + l.rank), 0) AS score
    FROM vector_hits v FULL JOIN lexical_hits l USING (chunk_pk)
)
SELECT c.chunk_pk, c.collection_id, c.chunk_id, n.local_id, c.title, c.body,
       c.source_url, c.locator,
       coalesce(citation.local_id, n.local_id),
       coalesce(citation.display_name, c.title),
       coalesce(citation.source_url, c.source_url, n.source_url),
       f.score::double precision, f.vector_rank, f.lexical_rank
FROM fused f
JOIN graphrag.chunks c USING (chunk_pk)
JOIN graphrag.nodes n USING (node_pk)
LEFT JOIN LATERAL (
    SELECT linked.local_id, linked.display_name, linked.source_url
    FROM graphrag.chunk_links cl
    JOIN graphrag.nodes linked ON linked.node_pk = cl.target_node_pk
    WHERE cl.chunk_pk = c.chunk_pk
    ORDER BY CASE cl.link_type
        WHEN 'SOURCE' THEN 1 WHEN 'DOCUMENT' THEN 2 WHEN 'PAGE' THEN 3
        WHEN 'PARENT' THEN 4 ELSE 5 END,
        linked.node_pk
    LIMIT 1
) citation ON true
ORDER BY f.score DESC, c.chunk_pk
LIMIT (SELECT n FROM bounded)
$$;

CREATE OR REPLACE FUNCTION graphrag_api.graph_neighbors(
    start_collection text,
    start_local_id text,
    max_depth integer DEFAULT 1,
    node_limit integer DEFAULT 100,
    predicate_allowlist text[] DEFAULT NULL
) RETURNS TABLE (
    depth integer, direction text, predicate text,
    collection_id text, local_id text, display_name text, source_url text
) LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, graphrag
SET statement_timeout = '5s'
AS $$
WITH RECURSIVE active AS (
    SELECT build_id FROM graphrag.active_corpus WHERE singleton
), start_node AS (
    SELECT n.node_pk, n.build_id FROM graphrag.nodes n JOIN active a USING (build_id)
    WHERE n.collection_id = start_collection AND n.local_id = start_local_id
), walk(node_pk, depth, direction, predicate, visited) AS (
    SELECT node_pk, 0, 'self'::text, 'SELF'::text, ARRAY[node_pk] FROM start_node
    UNION ALL
    SELECT CASE WHEN e.source_node_pk = w.node_pk THEN e.target_node_pk ELSE e.source_node_pk END,
           w.depth + 1,
           CASE WHEN e.source_node_pk = w.node_pk THEN 'out' ELSE 'in' END,
           e.predicate,
           w.visited || CASE WHEN e.source_node_pk = w.node_pk THEN e.target_node_pk ELSE e.source_node_pk END
    FROM walk w
    JOIN graphrag.edge_facts e ON e.source_node_pk = w.node_pk OR e.target_node_pk = w.node_pk
    JOIN active a ON a.build_id = e.build_id
    WHERE w.depth < greatest(0, least(coalesce(max_depth, 1), 3))
      AND (predicate_allowlist IS NULL OR e.predicate = ANY(predicate_allowlist[1:50]))
      AND NOT (CASE WHEN e.source_node_pk = w.node_pk THEN e.target_node_pk ELSE e.source_node_pk END = ANY(w.visited))
)
SELECT w.depth, w.direction, w.predicate, n.collection_id, n.local_id, n.display_name, n.source_url
FROM walk w JOIN graphrag.nodes n USING (node_pk)
ORDER BY w.depth, n.collection_id, n.local_id
LIMIT greatest(1, least(coalesce(node_limit, 100), 250))
$$;

CREATE OR REPLACE FUNCTION graphrag_api.route_tools(query_text text, result_limit integer DEFAULT 8)
RETURNS TABLE (collection_id text, name text, description text, input_schema jsonb, runtime text, score real)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, graphrag
SET statement_timeout = '3s'
AS $$
SELECT t.collection_id, t.name, t.description, t.input_schema, t.runtime,
       ts_rank_cd(t.search_tsv, websearch_to_tsquery('english', left(coalesce(query_text, ''), 1000))) AS score
FROM graphrag.tools t JOIN graphrag.active_corpus a USING (build_id)
WHERE t.search_tsv @@ websearch_to_tsquery('english', left(coalesce(query_text, ''), 1000))
ORDER BY score DESC, t.name
LIMIT greatest(1, least(coalesce(result_limit, 8), 20))
$$;

REVOKE ALL ON SCHEMA graphrag FROM PUBLIC;
REVOKE ALL ON SCHEMA graphrag_api FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA graphrag FROM PUBLIC;
REVOKE ALL ON FUNCTION graphrag.activate_build(text) FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA graphrag_api FROM PUBLIC;

COMMIT;

-- Grant only these API surfaces to the deployment role created by the operator:
-- GRANT USAGE ON SCHEMA graphrag_api TO graphrag_api_role;
-- GRANT EXECUTE ON FUNCTION graphrag_api.runtime_health() TO graphrag_api_role;
-- GRANT EXECUTE ON FUNCTION graphrag_api.hybrid_search(text,vector,integer,text[],text,double precision,double precision) TO graphrag_api_role;
-- GRANT EXECUTE ON FUNCTION graphrag_api.graph_neighbors(text,text,integer,integer,text[]) TO graphrag_api_role;
-- GRANT EXECUTE ON FUNCTION graphrag_api.route_tools(text,integer) TO graphrag_api_role;
