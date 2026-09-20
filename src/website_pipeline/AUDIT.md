# Website corpus audit

Final package validation: **passed**.

- 1,289 canonical pages: 933 Interactive Oceans, 315 Ocean Observatories Initiative, and 41 COSZO
- 2,981 bounded, heading-aware retrieval chunks
- 5 curated entity nodes and 11,443 traceable relationships
- 6,706 image records; 2,583 captioned figures downloaded locally
- 121 linked document records retained for later document extraction
- No duplicate page IDs or URLs, dangling graph edges, empty chunks, HTML markup in extracted page text, or unrelated-array names in accepted titles

The source index contained 3,208 WordPress records after recovering 98 records from a timed-out API batch. Relevance filtering excluded 1,959 pages and collapsed 13 exact-text aliases. Pages devoted to Pioneer, Endurance, Station Papa, Irminger, Global, NEPTUNE/Endeavour, and other non-target arrays were excluded.

Two old Interactive Oceans pages could not be retrieved after API, normal HTML, and alternate-URL attempts: `daily-log-from-visions-13` timed out without returning bytes and `live-high-definition-video-from-the-abyss` returned HTTP 500. Twelve captioned legacy images also remain remote failures (expired S3 paths, missing files, or obsolete host certificates); their URLs and captions remain in `figures.jsonl` with `status: failed`.

Source URLs remain in every page and chunk record for citation, refresh, and duplicate resolution. Uncaptioned images are represented as metadata only because they lack reliable local evidence for graph retrieval.
