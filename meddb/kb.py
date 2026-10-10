import hashlib
import json
from pathlib import Path

DEFAULT_DATA = Path(__file__).resolve().parents[1] / "data" / "abdominal-pain.json"
KINDS = {"Disease", "ClassificationCode", "Finding", "Mechanism", "Test", "Exposure"}
RELATIONS = {"has_phenotype": ({"Disease"}, {"Finding"}), "has_mechanism": ({"Disease"}, {"Mechanism"}), "causes": ({"Mechanism", "Exposure"}, {"Finding", "Mechanism", "Disease"}), "supports_finding": ({"Test"}, {"Finding"})}

class KB:
    def __init__(self, path=DEFAULT_DATA, version=None):
        if version is not None:
            if not isinstance(version, str) or not __import__('re').fullmatch(r'meddb-\d{4}\.\d{2}\.\d{2}\.\d+', version):
                raise ValueError("Invalid data version")
            path = DEFAULT_DATA.parent / "releases" / (version + ".json")
        path = Path(path)
        if not path.exists() and path.with_suffix(path.suffix + ".gz").exists():
            path = path.with_suffix(path.suffix + ".gz")
        raw = path.read_bytes()
        if path.suffix == ".gz":
            raw = __import__("gzip").decompress(raw)
        self.data = json.loads(raw)
        self.sha256 = hashlib.sha256(raw).hexdigest()
        self.version = self.data["version"]
        self.validate()
        self.nodes = {n["id"]: n for n in self.data["concepts"]}
        self.sources = {s["id"]: s for s in self.data["sources"]}

    def validate(self):
        if self.data.get("format") != 1:
            raise ValueError("Unsupported format")
        nodes = self.data["concepts"]
        by_id = {n["id"]: n for n in nodes}
        sources = {s["id"]: s for s in self.data["sources"]}
        if len(by_id) != len(nodes) or len(sources) != len(self.data["sources"]):
            raise ValueError("Duplicate ID")
        for node in nodes:
            if node["kind"] not in KINDS or not node["label_ko"] or not node["label_en"]:
                raise ValueError("Invalid concept")
            for mapping in node["mappings"]:
                if mapping.get("relation") not in {"exact", "broad", "narrow", "related"} or not mapping.get("target") or not mapping.get("source_id") in sources:
                    raise ValueError("Invalid mapping")
                if mapping.get('review_status') not in {'draft','reviewed','rejected'} or not mapping.get('source_version') or not mapping.get('target_label'):
                    raise ValueError("Missing mapping provenance")
                if mapping['review_status']=='reviewed' and not mapping.get('reviewer'):
                    raise ValueError("Reviewed mapping needs reviewer")
        seen = set()
        for a in self.data["assertions"]:
            if a["id"] in seen:
                raise ValueError("Duplicate assertion")
            seen.add(a["id"])
            if a["subject"] not in by_id or a["object"] not in by_id or a["source_id"] not in sources or not a["locator"]:
                raise ValueError("Missing assertion evidence or endpoint")
            if a["predicate"] not in RELATIONS:
                raise ValueError("Unknown predicate")
            sk, ok = RELATIONS[a["predicate"]]
            if by_id[a["subject"]]["kind"] not in sk or by_id[a["object"]]["kind"] not in ok:
                raise ValueError("Invalid relation endpoints")
            if a["review_status"] not in {"draft", "reviewed", "rejected"}:
                raise ValueError("Invalid review status")
            if a["review_status"] == "reviewed" and not a["reviewer"]:
                raise ValueError("Reviewed assertion needs reviewer")
            if a["frequency"] is not None:
                raise ValueError("Frequency schema is not implemented in format 1")
        return True

    def assertions(self, include_draft=False):
        return [a for a in self.data["assertions"] if a["review_status"] == "reviewed" or (include_draft and a["review_status"] == "draft")]

    def search(self, text, kind=None):
        q = text.casefold().strip()
        if kind is not None and kind not in KINDS:
            raise ValueError("Unknown kind")
        return [n for n in self.nodes.values() if (kind is None or n["kind"] == kind) and any(q in s.casefold() for s in [n["id"], n["label_ko"], n["label_en"], *n["aliases"], *[m["target"] for m in n["mappings"]], *[m["target_label"] for m in n["mappings"]]])]

    def graph(self, node, include_draft=False, depth=2, direction="both", source=None):
        if node not in self.nodes:
            raise ValueError("Unknown node")
        if not 0 <= depth <= 5 or direction not in {"both", "out", "in"}:
            raise ValueError("Invalid graph depth or direction")
        if source not in {None, "DisMech", "NIDDK"}:
            raise ValueError("Unknown source filter")
        assertions = self.assertions(include_draft)
        if source:
            assertions = [a for a in assertions if (a['source_id'].startswith('dismech:') if source=='DisMech' else a['source_id'].startswith('niddk-'))]
        adjacent = {}
        for a in assertions:
            if direction in {'both','out'}: adjacent.setdefault(a['subject'],[]).append(a)
            if direction in {'both','in'}: adjacent.setdefault(a['object'],[]).append(a)
        visited, frontier, edges = {node}, {node}, {}
        for _ in range(depth):
            next_nodes = set()
            for current in frontier:
                if current != node and direction=='out' and self.nodes[current]['kind'] in {'Finding','Test'}: continue
                if current != node and direction=='in' and self.nodes[current]['kind'] in {'Disease','Exposure'}: continue
                for a in adjacent.get(current,[]):
                    edges[a['id']]=a
                    next_nodes.update([a['subject'],a['object']])
            frontier = next_nodes - visited
            visited.update(next_nodes)
        used = {a['source_id'] for a in edges.values()}
        return dict(version=self.version, nodes=[self.nodes[k] for k in sorted(visited)], assertions=list(edges.values()), sources=[self.sources[k] for k in sorted(used)], traversal=direction+" explicit relationships; not causal inference")

    def rank(self, observations, include_draft=False, limit=30):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Limit must be between 1 and 100")
        if not isinstance(observations, dict):
            raise ValueError("Observations must be an object")
        for node, state in observations.items():
            if node not in self.nodes or self.nodes[node]["kind"] != "Finding" or state not in {"present", "absent", "unknown"}:
                raise ValueError("Invalid finding or observation state")
        grouped = {}
        for a in self.assertions(include_draft):
            if a["predicate"] == "has_phenotype": grouped.setdefault(a["subject"],[]).append(a)
        result = []
        for disease in self.search("", "Disease"):
            assertions = grouped.get(disease["id"], [])
            findings = {a["object"] for a in assertions}
            matched = sorted(n for n, state in observations.items() if state == "present" and n in findings)
            conflicts = sorted(n for n, state in observations.items() if state == "absent" and n in findings)
            if matched:
                evidence = [a for a in assertions if a["object"] in matched + conflicts]
                result.append(dict(disease=disease, matched=matched, conflicts=conflicts, evidence=evidence))
        result.sort(key=lambda r: (-len(r["matched"]), len(r["conflicts"]), r["disease"]["id"]))
        total_candidates = len(result)
        result = result[:limit]
        return dict(version=self.version, sha256=self.sha256, total_candidates=total_candidates, interpretation="Direct phenotype overlap; not a diagnostic probability. Absence is not exclusion.", include_draft=include_draft, candidates=result, sources=[self.sources[s] for s in sorted({a["source_id"] for r in result for a in r["evidence"]})])

    TOOLS = [
        {"name": "search", "description": "Search concepts by Korean or English name; return stable IDs.", "input_schema": {"type": "object", "properties": {"text": {"type": "string"}, "kind": {"type": "string", "enum": sorted(KINDS)}}, "required": ["text"], "additionalProperties": False}},
        {"name": "graph", "description": "Evidence-bearing undirected neighborhood, not causal inference. Drafts excluded by default.", "input_schema": {"type": "object", "properties": {"node": {"type": "string"}, "direction": {"type": "string", "enum": ["in", "out", "both"]}, "depth": {"type": "integer", "minimum": 0, "maximum": 5}, "include_draft": {"type": "boolean"}}, "required": ["node"], "additionalProperties": False}},
        {"name": "rank", "description": "Direct phenotype overlap, not diagnosis probability; unknown observations are ignored.", "input_schema": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}, "observations": {"type": "object", "additionalProperties": {"type": "string", "enum": ["present", "absent", "unknown"]}}, "include_draft": {"type": "boolean"}}, "required": ["observations"], "additionalProperties": False}}
    ]

    def call(self, name, args):
        if name not in {t["name"] for t in self.TOOLS} or not isinstance(args, dict):
            raise ValueError("Invalid tool call")
        return dict(version=self.version, sha256=self.sha256, result=getattr(self, name)(**args))
