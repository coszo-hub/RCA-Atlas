-- Full-text layer, part 2. The main search also leaves out chunks marked retrieval_layer (the papers RCA
-- Information carries in full, beyond each one's first chunk), and paper_passages searches the layer within the
-- papers the main evidence found. CREATE OR REPLACE keeps hybrid_search's signature and grants.
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
      AND (CASE WHEN collection_filter IS NULL THEN c.collection_id NOT LIKE '%\_fulltext' ESCAPE '\'
                                              AND NOT (c.metadata ? 'retrieval_layer')
               ELSE c.collection_id = ANY(collection_filter[1:20]) END)
    ORDER BY e.embedding <=> query_embedding
    LIMIT (SELECT n * 4 FROM bounded)
), lexical_hits AS (
    SELECT c.chunk_pk,
           row_number() OVER (ORDER BY ts_rank_cd(c.search_tsv, websearch_to_tsquery('english', left(coalesce(query_text, ''), 1000))) DESC) AS rank
    FROM graphrag.chunks c
    JOIN active a USING (build_id), bounded b
    WHERE c.search_tsv @@ websearch_to_tsquery('english', left(coalesce(query_text, ''), 1000))
      AND (CASE WHEN collection_filter IS NULL THEN c.collection_id NOT LIKE '%\_fulltext' ESCAPE '\'
                                              AND NOT (c.metadata ? 'retrieval_layer')
               ELSE c.collection_id = ANY(collection_filter[1:20]) END)
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

-- A paper's passages in the full-text layer: the *_fulltext collections and chunks marked retrieval_layer, kept to
-- the papers named by paper_keys (DOI or document ID). Each paper has some tens of passages, so the vector ranking
-- is exact, and the lexical ranking matches any of the question's words (a long question rarely has a passage with
-- all of them), which picks the passage that states the asked fact.
CREATE OR REPLACE FUNCTION graphrag_api.paper_passages(
    query_text text,
    query_embedding vector(384),
    paper_keys text[],
    result_limit integer DEFAULT 12,
    model_filter text DEFAULT 'BAAI/bge-small-en-v1.5'
) RETURNS TABLE (
    chunk_pk bigint, collection_id text, chunk_id text, node_local_id text,
    title text, body text, source_url text, locator text,
    citation_source_id text, citation_title text, citation_url text,
    places jsonb, score double precision, vector_rank bigint, lexical_rank bigint
) LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, graphrag, public
SET statement_timeout = '5s'
AS $$
WITH active AS (
    SELECT build_id FROM graphrag.active_corpus WHERE singleton
), cand AS (
    SELECT c.chunk_pk, c.search_tsv,
           (SELECT e.embedding <=> query_embedding FROM graphrag.embeddings e
            WHERE e.chunk_pk = c.chunk_pk AND e.model_id = coalesce(model_filter, 'BAAI/bge-small-en-v1.5') LIMIT 1) AS distance
    FROM graphrag.chunks c JOIN active a USING (build_id)
    WHERE (c.collection_id LIKE '%\_fulltext' ESCAPE '\' OR c.metadata ? 'retrieval_layer')
      AND c.metadata->'paper_keys' ?| (paper_keys[1:12])
), word AS (
    -- The question's stemmed words, each weighted by how rare it is among these passages: a word in every passage
    -- of the paper (its topic) tells nothing; one in two passages points at them.
    SELECT w.lexeme, quote_literal(w.lexeme)::tsquery AS tq
    FROM (SELECT DISTINCT unnest(tsvector_to_array(to_tsvector('english', left(coalesce(query_text, ''), 1000)))) AS lexeme) w
), weight AS (
    SELECT word.tq, ln(((SELECT count(*) FROM cand) + 1.0) / (count(cand.chunk_pk) + 0.5)) AS idf
    FROM word LEFT JOIN cand ON cand.search_tsv @@ word.tq
    GROUP BY word.tq
    HAVING count(cand.chunk_pk) > 0
), lexical AS (
    SELECT cand.chunk_pk, row_number() OVER (ORDER BY sum(weight.idf) DESC) AS lexical_rank
    FROM cand JOIN weight ON cand.search_tsv @@ weight.tq
    GROUP BY cand.chunk_pk
), ranked AS (
    SELECT cand.chunk_pk, row_number() OVER (ORDER BY cand.distance NULLS LAST) AS vector_rank, l.lexical_rank
    FROM cand LEFT JOIN lexical l USING (chunk_pk)
), fused AS (
    SELECT chunk_pk, vector_rank, lexical_rank,
           0.4 / (60 + vector_rank) + coalesce(0.6 / (60 + lexical_rank), 0) AS score
    FROM ranked
)
SELECT c.chunk_pk, c.collection_id, c.chunk_id, n.local_id, c.title, c.body, c.source_url, c.locator,
       coalesce(citation.local_id, n.local_id), coalesce(citation.display_name, c.title),
       coalesce(citation.source_url, c.source_url, n.source_url),
       coalesce(c.metadata->'places', '[]'::jsonb),
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
LIMIT greatest(1, least(coalesce(result_limit, 12), 30))
$$;

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'graphrag_api_role') THEN
        GRANT EXECUTE ON FUNCTION graphrag_api.paper_passages(text, vector, text[], integer, text) TO graphrag_api_role;
    END IF;
END $$;
