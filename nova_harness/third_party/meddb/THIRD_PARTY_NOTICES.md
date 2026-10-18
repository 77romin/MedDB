# Third-party data notices

DisMech — Monarch Initiative, https://dismech.monarchinitiative.org/ , https://github.com/monarch-initiative/dismech . Website data attribution: CC-BY 4.0 (https://creativecommons.org/licenses/by/4.0/). Repository LICENSE: BSD-3-Clause; full notice retained in licenses/DisMech-BSD-3-Clause.txt.

Data pinned to commit 0cfe4bd579700d42c13d5fcc147e785e52c97966. NOVA imports explicit disease/phenotype/mechanism and named downstream relationships. Original evidence quotations are omitted. Source document location and supporting reference IDs are retained. Local translations are draft AI translations; untranslated names remain English. Import does not mean clinical review or independent verification of references. All imported relationships remain draft. No endorsement is implied.

HPO — Human Phenotype Ontology Consortium, Peter Robinson, Sebastian Köhler, Monarch Initiative. Official OBO hp/releases/2026-09-01, https://purl.obolibrary.org/obo/hp.obo . Only identifiers, labels and mapping verification metadata are used. HPOA disease annotation file is not imported.

NIDDK — source URLs and accessed versions accompany each original pilot claim. No full pages or article quotations are copied.

The BBI-BBO viewer was visually inspected as a design reference. Its application code, fonts and bundled dataset were not copied into NOVA.


## Optional guideline reader adaptation (2026-10-18)

`nova_agent/guidelines.py` adapts the read-only metadata retrieval code from
`meddb/guidelines.py` at commit `63743a8b8a2e278b426d18fc040e880740318ae3`.
It adds a server-path default and a title-matching fallback when SQLite FTS5 is unavailable.
The official guideline corpus is not included in this repository or submission archive.
Runtime source excerpts retain the document URL, organization, year, license, path, lines and hash.
