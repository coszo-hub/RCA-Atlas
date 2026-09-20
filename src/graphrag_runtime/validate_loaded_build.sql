DO $$
DECLARE
    candidate text;
    actual bigint;
BEGIN
    SELECT build_id INTO candidate FROM graphrag.active_corpus WHERE singleton;
    IF candidate IS NULL THEN RAISE EXCEPTION 'no active corpus build'; END IF;

    SELECT count(*) INTO actual FROM graphrag.collections WHERE build_id=candidate;
    IF actual <> 13 THEN RAISE EXCEPTION 'collections: expected 13, got %', actual; END IF;
    SELECT count(*) INTO actual FROM graphrag.nodes WHERE build_id=candidate;
    IF actual <> 21938 THEN RAISE EXCEPTION 'nodes: expected 21938, got %', actual; END IF;
    SELECT count(*) INTO actual FROM graphrag.node_records r JOIN graphrag.source_files f USING(source_file_pk) WHERE f.build_id=candidate;
    IF actual <> 23404 THEN RAISE EXCEPTION 'node records: expected 23404, got %', actual; END IF;
    SELECT count(*) INTO actual FROM graphrag.chunks WHERE build_id=candidate;
    IF actual <> 6565 THEN RAISE EXCEPTION 'chunks: expected 6565, got %', actual; END IF;
    SELECT count(*) INTO actual FROM graphrag.chunks WHERE build_id=candidate AND search_tsv IS NOT NULL;
    IF actual <> 6565 THEN RAISE EXCEPTION 'FTS rows: expected 6565, got %', actual; END IF;
    SELECT count(*) INTO actual FROM graphrag.edge_records r JOIN graphrag.source_files f USING(source_file_pk) WHERE f.build_id=candidate;
    IF actual <> 30242 THEN RAISE EXCEPTION 'edge records: expected 30242, got %', actual; END IF;
    SELECT count(*) INTO actual FROM graphrag.edge_facts WHERE build_id=candidate;
    IF actual <> 29538 THEN RAISE EXCEPTION 'edge facts: expected 29538, got %', actual; END IF;
    SELECT count(*) INTO actual FROM graphrag.structured_records r JOIN graphrag.source_files f USING(source_file_pk) WHERE f.build_id=candidate;
    IF actual <> 76984 THEN RAISE EXCEPTION 'structured records: expected 76984, got %', actual; END IF;
    SELECT count(*) INTO actual
    FROM graphrag.embeddings e JOIN graphrag.chunks c USING(chunk_pk)
    WHERE c.build_id=candidate AND e.model_id='BAAI/bge-small-en-v1.5'
      AND e.dimensions=384 AND e.text_sha256=c.text_sha256;
    IF actual <> 6565 THEN RAISE EXCEPTION 'fresh embeddings: expected 6565, got %', actual; END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.tables t
        WHERE t.table_schema='graphrag'
          AND has_table_privilege('graphrag_api_role', format('%I.%I',t.table_schema,t.table_name), 'SELECT')
    ) THEN RAISE EXCEPTION 'API role has direct base-table SELECT privilege'; END IF;
END
$$;

SELECT b.build_id, b.catalog_fingerprint_sha256, b.validation_passed,
       (SELECT count(*) FROM graphrag.chunks c WHERE c.build_id=b.build_id) AS chunks,
       (SELECT count(*) FROM graphrag.embeddings e JOIN graphrag.chunks c USING(chunk_pk) WHERE c.build_id=b.build_id) AS embeddings
FROM graphrag.corpus_builds b
JOIN graphrag.active_corpus a USING(build_id);
