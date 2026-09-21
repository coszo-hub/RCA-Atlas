# RCA and COSZO instrument inventory pipeline

`build_instrument_inventory.py` compiles instrument-level records already present in the project's RCA Information collection (preserved upstream Arcada provenance), Websites, Literature, COSZO document, workbook, and StationXML collections.

The inventory preserves six source distinctions:

- RCA instrument or deployment records catalogued by RCA Information;
- the site-specific COSZO sensor suite;
- additional confirmed RCA PI instruments;
- time-bounded RCA experiments;
- reference-only instrument identifiers;
- COSZO-related assets listed in the deployment-site workbook without a stated operational status.

Science junction boxes are written to `infrastructure.jsonl` and excluded from instrument counts. The builder does not infer current operational status from a catalogue entry. COSZO's four-unit workbook totals are reconciled with the three new-node units on the COSZO website by retaining the Oregon Shelf APG/current-meter records as workbook-specified and attaching the evidence for each claim.

The runtime package belongs under `data/Instruments`. This builder belongs under `src/instrument_inventory`.
