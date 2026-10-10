from pathlib import Path
from .rdf import export

ROOT = Path(__file__).resolve().parents[1]
def validate_rdf(kb, include_draft=False, node=None):
    try:
        from rdflib import Graph
        from pyshacl import validate
    except ImportError as exc:
        raise RuntimeError('Install requirements-ontology.txt in a virtual environment') from exc
    scope = "full snapshot"
    if node:
        from types import SimpleNamespace
        neighborhood = kb.graph(node, include_draft, 2, "out")
        assertions = neighborhood['assertions']
        selected_nodes = {n['id']: n for n in neighborhood['nodes']}
        source_ids = {a['source_id'] for a in assertions} | {m['source_id'] for n in selected_nodes.values() for m in n['mappings']}
        kb = SimpleNamespace(nodes=selected_nodes, sources={s:kb.sources[s] for s in source_ids}, version=kb.version, sha256=kb.sha256, assertions=lambda include_draft:assertions)
        scope = "outgoing neighborhood: " + node
    graph = Graph().parse(data=export(kb, include_draft), format='turtle')
    shapes = Graph().parse(ROOT / 'ontology' / 'shapes.ttl', format='turtle')
    ontology = Graph().parse(ROOT / 'ontology' / 'core.ttl', format='turtle')
    conforms, report, text = validate(graph, shacl_graph=shapes, ont_graph=ontology, inference='none', meta_shacl=True)
    return dict(conforms=bool(conforms), scope=scope, version=kb.version, sha256=kb.sha256, triples=len(graph), report=text)
