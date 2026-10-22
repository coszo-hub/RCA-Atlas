-- Retrieval layers. A collection whose ID ends in _fulltext (the full text of literature papers) is searched only
-- when a request names it in collection_filter; a search without a filter leaves it out. Its passages add to answers
-- about papers the main search found, without displacing instruments, websites or abstracts from that search.
-- CREATE OR REPLACE keeps the function's signature and grants.
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

-- Graph neighbours, bounded by fan-out. The recursive walk enumerated every path before its LIMIT, and hub nodes
-- (an entity with ~2,000 edges, site pages with 300-650) made two hops run past the 5 s statement timeout. Each step
-- now follows at most 25 edges per node and direction, through the (build_id, source/target) indexes, and returns
-- each node once at its nearest depth.
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
WITH active AS (
    SELECT build_id FROM graphrag.active_corpus WHERE singleton
), start_node AS (
    SELECT n.node_pk, n.build_id FROM graphrag.nodes n JOIN active a USING (build_id)
    WHERE n.collection_id = start_collection AND n.local_id = start_local_id
), bounds AS (
    SELECT greatest(0, least(coalesce(max_depth, 1), 3)) AS max_d
), step1 AS (
    SELECT DISTINCT ON (x.node_pk) x.node_pk, 1 AS depth, x.direction, x.predicate
    FROM start_node s CROSS JOIN bounds b CROSS JOIN LATERAL (
        (SELECT e.target_node_pk AS node_pk, 'out'::text AS direction, e.predicate FROM graphrag.edge_facts e
         WHERE e.build_id = s.build_id AND e.source_node_pk = s.node_pk
           AND (predicate_allowlist IS NULL OR e.predicate = ANY(predicate_allowlist[1:50]))
         ORDER BY e.target_node_pk LIMIT 25)
        UNION ALL
        (SELECT e.source_node_pk, 'in'::text, e.predicate FROM graphrag.edge_facts e
         WHERE e.build_id = s.build_id AND e.target_node_pk = s.node_pk
           AND (predicate_allowlist IS NULL OR e.predicate = ANY(predicate_allowlist[1:50]))
         ORDER BY e.source_node_pk LIMIT 25)
    ) x
    WHERE b.max_d >= 1 AND x.node_pk <> s.node_pk
    ORDER BY x.node_pk, x.direction
), step2 AS (
    SELECT DISTINCT ON (x.node_pk) x.node_pk, 2 AS depth, x.direction, x.predicate
    FROM step1 p CROSS JOIN start_node s CROSS JOIN bounds b CROSS JOIN LATERAL (
        (SELECT e.target_node_pk AS node_pk, 'out'::text AS direction, e.predicate FROM graphrag.edge_facts e
         WHERE e.build_id = s.build_id AND e.source_node_pk = p.node_pk
           AND (predicate_allowlist IS NULL OR e.predicate = ANY(predicate_allowlist[1:50]))
         ORDER BY e.target_node_pk LIMIT 25)
        UNION ALL
        (SELECT e.source_node_pk, 'in'::text, e.predicate FROM graphrag.edge_facts e
         WHERE e.build_id = s.build_id AND e.target_node_pk = p.node_pk
           AND (predicate_allowlist IS NULL OR e.predicate = ANY(predicate_allowlist[1:50]))
         ORDER BY e.source_node_pk LIMIT 25)
    ) x
    WHERE b.max_d >= 2 AND x.node_pk <> s.node_pk AND x.node_pk NOT IN (SELECT node_pk FROM step1)
    ORDER BY x.node_pk, x.direction
), step3 AS (
    SELECT DISTINCT ON (x.node_pk) x.node_pk, 3 AS depth, x.direction, x.predicate
    FROM step2 p CROSS JOIN start_node s CROSS JOIN bounds b CROSS JOIN LATERAL (
        (SELECT e.target_node_pk AS node_pk, 'out'::text AS direction, e.predicate FROM graphrag.edge_facts e
         WHERE e.build_id = s.build_id AND e.source_node_pk = p.node_pk
           AND (predicate_allowlist IS NULL OR e.predicate = ANY(predicate_allowlist[1:50]))
         ORDER BY e.target_node_pk LIMIT 25)
        UNION ALL
        (SELECT e.source_node_pk, 'in'::text, e.predicate FROM graphrag.edge_facts e
         WHERE e.build_id = s.build_id AND e.target_node_pk = p.node_pk
           AND (predicate_allowlist IS NULL OR e.predicate = ANY(predicate_allowlist[1:50]))
         ORDER BY e.source_node_pk LIMIT 25)
    ) x
    WHERE b.max_d >= 3 AND x.node_pk <> s.node_pk
      AND x.node_pk NOT IN (SELECT node_pk FROM step1) AND x.node_pk NOT IN (SELECT node_pk FROM step2)
    ORDER BY x.node_pk, x.direction
), walk AS (
    SELECT node_pk, 0 AS depth, 'self'::text AS direction, 'SELF'::text AS predicate FROM start_node
    UNION ALL SELECT * FROM step1 UNION ALL SELECT * FROM step2 UNION ALL SELECT * FROM step3
)
SELECT w.depth, w.direction, w.predicate, n.collection_id, n.local_id, n.display_name, n.source_url
FROM walk w JOIN graphrag.nodes n USING (node_pk)
ORDER BY w.depth, n.collection_id, n.local_id
LIMIT greatest(1, least(coalesce(node_limit, 100), 250))
$$;
