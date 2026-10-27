-- Indexes on the foreign keys that cascade when a corpus build is deleted. Without them each deleted node scanned
-- the edge, link and record tables in full: deleting 33 superseded builds ran two days without finishing, and with
-- them took 12 seconds a build. Builds pile up on every load (35 by 2026-10-24, 17 GB), and the vector index spans
-- them all, so searches filtered to the active build timed out.
CREATE INDEX IF NOT EXISTS edge_records_source_node_idx ON graphrag.edge_records (source_node_pk);
CREATE INDEX IF NOT EXISTS edge_records_target_node_idx ON graphrag.edge_records (target_node_pk);
CREATE INDEX IF NOT EXISTS edge_facts_source_node_idx ON graphrag.edge_facts (source_node_pk);
CREATE INDEX IF NOT EXISTS edge_facts_target_node_idx ON graphrag.edge_facts (target_node_pk);
CREATE INDEX IF NOT EXISTS chunk_links_target_node_idx ON graphrag.chunk_links (target_node_pk);
CREATE INDEX IF NOT EXISTS node_records_node_idx ON graphrag.node_records (node_pk);
