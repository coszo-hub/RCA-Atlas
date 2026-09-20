# OOI M2M tool sources and licensing

The live agent adapter in `ooi_m2m_agent_tools.py` is an independent,
standard-library implementation of the public OOI M2M HTTP interface. It does
not import either reference project at runtime and does not place their source
code in the GraphRAG corpus.

The design was checked against these pinned source versions:

| Project | Commit | License | Patterns used as design references |
| --- | --- | --- | --- |
| [reedan88/OOINet](https://github.com/reedan88/OOINet/tree/2168c825d832cbb913f138b59fd8f2a82dc36dfc) | `2168c825d832cbb913f138b59fd8f2a82dc36dfc` | GPL-3.0 | Instrument discovery, vocabulary, deployments, methods/streams, request URLs, async status, and catalog/download flow |
| [ooi-data/ooi-harvester](https://github.com/ooi-data/ooi-harvester/tree/f4d4e467624006ea315bc823595e7951de368d1f) | `f4d4e467624006ea315bc823595e7951de368d1f` | MIT, Copyright 2022 University of Washington, Cabled Array Value Added Team | Estimate metadata, durable request state, `status.txt`, THREDDS parsing, and bounded pipeline stages |

Complete snapshots, including their original license files, are stored under
`source_material/repositories/ooi-m2m/`. They are source references rather than
retrieval documents. Compact provenance records in `data/COSZOHub` let the
graph link the agent tools to the exact versions used during implementation.

The live adapter reads OOI credentials from `OOI_USERNAME` and `OOI_TOKEN`.
Credential values are never added to URLs, returned from tools, or written to
request state.
