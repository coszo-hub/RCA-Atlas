-- Chunks of one collection by their ids ("ooi_assets_RS03CCAL-MJ03F-05-BOTPTA301").
--
-- The OOI asset-management collection names each chunk after what it holds: an instrument's reference designator, a
-- cruise, a site, a depth band. Search ranks those few hundred chunks below web pages on the same instrument, and its
-- lexical half does not match hyphenated designators, so the Worker asks for the chunks it knows by id. At most 12
-- ids, of one collection, in the active corpus.

CREATE OR REPLACE FUNCTION graphrag_api.chunks_by_id(
    wanted_collection text,
    ids text[]
) RETURNS TABLE (
    chunk_pk bigint, collection_id text, chunk_id text, node_local_id text,
    title text, body text, source_url text, locator text,
    citation_source_id text, citation_title text, citation_url text, places jsonb
) LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, graphrag, public
SET statement_timeout = '3s'
AS $$
WITH active AS (
    SELECT build_id FROM graphrag.active_corpus WHERE singleton
), wanted AS (
    SELECT id, ord FROM unnest(ids[1:12]) WITH ORDINALITY AS t(id, ord)
)
SELECT c.chunk_pk, c.collection_id, c.chunk_id, n.local_id, c.title, c.body, c.source_url, c.locator,
       coalesce(citation.local_id, n.local_id), coalesce(citation.display_name, c.title),
       coalesce(citation.source_url, c.source_url, n.source_url),
       coalesce(c.metadata->'places', '[]'::jsonb)
FROM wanted w
JOIN graphrag.chunks c ON c.chunk_id = w.id AND c.collection_id = wanted_collection
JOIN active a ON a.build_id = c.build_id
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
ORDER BY w.ord
$$;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'graphrag_api_role') THEN
        GRANT EXECUTE ON FUNCTION graphrag_api.chunks_by_id(text, text[]) TO graphrag_api_role;
    END IF;
END $$;
