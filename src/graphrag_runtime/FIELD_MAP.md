# Unified corpus normalization map

The catalog fingerprint audited for this mapping is
`8a63f8edf5b5d89fe43662bf463f1a1a728056eb62f4a1bde2aee90f00743680`.
The loader must use `(build_id, collection_id, local_id)` as logical node
identity. It must preserve every JSONL row in `node_records` or
`edge_records`; raw IDs are not globally unique.

| Collection | Node file -> local ID | Chunk links | Edge mapping |
|---|---|---|---|
| arcada | documents->document_id; chunks->chunk_id; entities->entity_id; source_documents->source_document_id | document_id, parent_id | source_id, predicate, target_id; no raw edge ID |
| axial_earthquakes | chunks->chunk_id; entities->entity_id; sources->source_id | entity_ids[], source_ids[] | relationship_id; source_id, relationship_type, target_id |
| coszo_documents | chunks->chunk_id; entities->entity_id; figures->figure_id; pages->page_id; source_documents->source_id; documents->document_id | document_id, page_id, source_id, entity_ids[] | relationship_id; source_id, relationship_type, target_id |
| coszo_hub | chunks/entities/figures/repositories/tools->id | entity_ids[] | id; from, predicate, to |
| datasheets | source_documents->source_id; documents->document_id; pages->page_id; figures->figure_id; entities->entity_id; chunks->chunk_id | document_id, page_id, source_id, entity_ids[] | relationship_id; source_id, predicate, target_id |
| figures | figures->figure_id; entities->entity_id; sources->source_id; chunks->chunk_id | document_id, parent_id, source_id, entity_ids[] | relationship_id; source_id, predicate, target_id |
| instruments | entities/instrument_types->entity_id; sources->source_id; instruments->instrument_id; chunks->chunk_id; infrastructure->infrastructure_id | document_id, parent_id | source_id, predicate, target_id; no raw edge ID |
| literature | documents->document_id; entities->entity_id; chunks->chunk_id; source_documents->source_document_id | document_id, parent_id when present | source_id, predicate, target_id; no raw edge ID |
| nereus | sources->source_id; entities->entity_id; observations->observation_id; chunks->chunk_id | document_id, parent_id | relationship_id; source_id, predicate, target_id |
| pi_portal | instruments->instrument_id; endpoints->endpoint_id; sites->site_id; sources->source_id; tools->tool_id; entities->entity_id; chunks->chunk_id | document_id, parent_id, source_ids[] | relationship_id; source_id, predicate, target_id |
| qaqc | sources->source_id; entities->entity_id; capabilities->capability_id; chunks->chunk_id | document_id, parent_id | relationship_id; source_id, predicate, target_id |
| station_metadata | chunks->chunk_id; entities->entity_id; channels->channel_id; stations->station_id; source_documents->source_id | entity_ids[], source_ids[] | relationship_id; source_id, relationship_type, target_id |
| websites | chunks->chunk_id; entities->entity_id; figures->figure_id; pages->page_id | page_id | source_id, predicate, target_id; no raw edge ID |

Chunk text is `text`; COSZO Hub uses `id`, not `chunk_id`. Search title uses
`title`, then the linked parent title when absent. Section text comes from
`section_heading` or the ordered `section_headings` array. Position maps from
`position`, `position_on_page`, or `chunk_ordinal_on_page`. Locator maps from
`locator`; URLs map from `source_url`.

Display names use `title`, `name`, `label`, `filename`, `channel`, then
`local_id`. Store the source filename stem as each node record's kind. A
logical node may have several kinds. Preserve all fields not promoted to a
column in JSONB. Preserve `source_is_untrusted_data` as nullable raw provenance
and set `effective_untrusted=true` when it is absent.

Identifiers come from the primary ID plus `aliases[]`, `canonical_id`,
`shared_canonical_id`, `all_known_shared_instrument_ids`, DOI, instrument or
reference designators, and FDSN network/station fields. Cross-collection
`identity_members` require explicit evidence from `external_dataset`, a
canonical/shared ID declaration, or `instrument_crosswalk.jsonl`. Never merge
nodes merely because their raw IDs match: 71 raw IDs occur in more than one
collection.

Structured sidecars remain in `structured_records`: Axial daily/monthly
summaries use `summary_id`; COSZO Hub diagnostics/metrics use `id`; Literature
citations use `occurrence_id`, glossary uses `term_id`, and literature uses
`id`; Nereus engineering uses `observation_id`, crosswalk uses the composite
`nereus_entity_id/reference_designator`, and notes use `entity_id/note_id`;
QAQC HITL uses a file-line synthetic ID; Website linked documents use
`page_id/url`. Auxiliary Axial visual chunks are not part of the canonical
6,565-chunk embedding set.

Expected physical/logical node counts are: arcada 1,132/1,132; axial 190/189;
COSZO documents 2,516/2,516; COSZO Hub 3,161/2,136; datasheets 1,269/1,269;
figures 63/63; instruments 480/438; literature 942/942; Nereus 1,728/1,728;
PI portal 84/84; QAQC 33/33; station metadata 825/427; websites
10,981/10,981. Total: 23,404 source records and 21,938 logical nodes.

Important irregularities: `schema_version` is null for Axial and Station
Metadata; Arcada `units`, Literature `license`/`notes`, and COSZO metric
`figure_generated` have mixed JSON types; COSZO document chunks lack titles;
Nereus repeats 151 relationship rows exactly; Website figure rows include
failed and unavailable downloads; IDs contain `:`, `@`, and hyphens and must
not be parsed from concatenated keys.
