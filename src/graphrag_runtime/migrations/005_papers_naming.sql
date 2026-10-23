-- Papers whose full text names an instrument code ("which papers used AXEC1 and AXEC2?").
--
-- No abstract names a seismic station; the full text of nine papers names AXEC1 or AXEC2. The passage search only
-- searches within papers the main evidence already holds, so this asks the whole full-text layer, by literal whole
-- word match (case-sensitive: station codes and reference designators are written in capitals). One row per paper:
-- the passage naming the terms most, and how many of the paper's passages name them, most first.

CREATE OR REPLACE FUNCTION graphrag_api.papers_naming(
    terms text[],
    result_limit integer DEFAULT 10
) RETURNS TABLE (
    chunk_pk bigint, collection_id text, chunk_id text, node_local_id text,
    title text, body text, source_url text, locator text,
    citation_source_id text, citation_title text, citation_url text,
    places jsonb, paper_key text, passages_naming integer, terms_named text[]
) LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, graphrag, public
SET statement_timeout = '5s'
AS $$
WITH active AS (
    SELECT build_id FROM graphrag.active_corpus WHERE singleton
), wanted AS (
    -- Codes only: letters, digits and hyphens, 3 to 40 characters, at most six.
    SELECT DISTINCT t AS term FROM unnest(terms[1:6]) t WHERE t ~ '^[A-Za-z0-9-]{3,40}$'
), layer AS MATERIALIZED (
    -- The full-text layer, read once for all the terms (one scan per term took 1.8 s each).
    SELECT c.chunk_pk, c.body, c.metadata->'paper_keys'->>0 AS paper_key
    FROM graphrag.chunks c JOIN active a USING (build_id)
    WHERE (c.collection_id LIKE '%\_fulltext' ESCAPE '\' OR c.metadata ? 'retrieval_layer')
      AND c.metadata ? 'paper_keys'
), hit AS (
    SELECT l.chunk_pk, l.paper_key, w.term,
           (length(l.body) - length(replace(l.body, w.term, ''))) / length(w.term) AS n
    FROM layer l JOIN wanted w
      ON strpos(l.body, w.term) > 0 AND l.body ~ ('(^|[^A-Za-z0-9])' || w.term || '($|[^A-Za-z0-9])')
), per_chunk AS (
    SELECT chunk_pk, paper_key, sum(n) AS n, array_agg(DISTINCT term ORDER BY term) AS terms_named FROM hit GROUP BY chunk_pk, paper_key
), per_paper AS (
    SELECT paper_key, count(DISTINCT chunk_pk)::integer AS passages_naming,
           (array_agg(chunk_pk ORDER BY n DESC, chunk_pk))[1] AS best,
           array_agg(DISTINCT t ORDER BY t) AS terms_named
    FROM per_chunk, unnest(per_chunk.terms_named) t GROUP BY paper_key
)
SELECT c.chunk_pk, c.collection_id, c.chunk_id, n.local_id, c.title, c.body, c.source_url, c.locator,
       coalesce(citation.local_id, n.local_id), coalesce(citation.display_name, c.title),
       coalesce(citation.source_url, c.source_url, n.source_url),
       coalesce(c.metadata->'places', '[]'::jsonb),
       p.paper_key, p.passages_naming, p.terms_named
FROM per_paper p
JOIN graphrag.chunks c ON c.chunk_pk = p.best
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
ORDER BY cardinality(p.terms_named) DESC, p.passages_naming DESC, p.paper_key
LIMIT greatest(1, least(coalesce(result_limit, 10), 20))
$$;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'graphrag_api_role') THEN
        GRANT EXECUTE ON FUNCTION graphrag_api.papers_naming(text[], integer) TO graphrag_api_role;
    END IF;
END $$;
