import hashlib
import json
from pathlib import Path

DATA_ROOT = Path(__file__).resolve().parents[1] / 'data'
DEFAULT_DATA = DATA_ROOT / 'releases' / 'meddb-2026.10.10.4.json.gz'
DEFAULT_VERSION = 'meddb-2026.10.13.1'
KINDS = {"Disease", "ClassificationCode", "Finding", "Mechanism", "Test", "Exposure"}
RELATIONS = {"has_phenotype": ({"Disease"}, {"Finding"}), "has_mechanism": ({"Disease"}, {"Mechanism"}), "causes": ({"Mechanism", "Exposure"}, {"Finding", "Mechanism", "Disease"}), "supports_finding": ({"Test"}, {"Finding"})}

class KB:
    def __init__(self, path=None, version=None):
        if path is None:
            path = DEFAULT_DATA
            if version is None and (DATA_ROOT/'releases'/(DEFAULT_VERSION+'.json.gz')).exists():
                version = DEFAULT_VERSION
        if version is not None:
            if not isinstance(version, str) or not __import__('re').fullmatch(r'meddb-\d{4}\.\d{2}\.\d{2}\.\d+', version):
                raise ValueError("Invalid data version")
            path = DATA_ROOT / "releases" / (version + ".json")
        path = Path(path)
        if not path.exists() and path.with_suffix(path.suffix + ".gz").exists():
            path = path.with_suffix(path.suffix + ".gz")
        self.path = path
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
            if 'clinical_constraints' in node:
                import math
                c = node['clinical_constraints']
                if node['kind'] != 'Disease' or not isinstance(c, dict) or set(c) - {'min_age','max_age','sex','review_status','reviewer','source_id','locator'}:
                    raise ValueError('Invalid clinical constraints')
                for field in ('min_age', 'max_age'):
                    value = c.get(field)
                    if value is not None and (type(value) not in {int,float} or not math.isfinite(value) or not 0 <= value <= 130):
                        raise ValueError('Invalid age constraint')
                if c.get('min_age') is not None and c.get('max_age') is not None and c['min_age'] > c['max_age']:
                    raise ValueError('Inverted age constraint')
                if c.get('sex') not in {None,'female','male'} or c.get('review_status') not in {'draft','reviewed','rejected'} or c.get('source_id') not in sources or not c.get('locator'):
                    raise ValueError('Missing clinical constraint provenance')
                if c['review_status'] == 'reviewed' and not c.get('reviewer'):
                    raise ValueError('Reviewed clinical constraints need reviewer')
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
            if 'polarity' in a:
                if a['polarity'] not in {'associated','excluded'}:
                    raise ValueError('Invalid assertion polarity')
                if str(a.get('frequency_label','')).strip().upper()=='EXCLUDED' and a['polarity']!='excluded':
                    raise ValueError('Polarity contradicts EXCLUDED marker')
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

    def rank(self, observations, include_draft=False, limit=30, patient=None, category=None):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Limit must be between 1 and 100")
        if not isinstance(observations, dict):
            raise ValueError("Observations must be an object")
        for node, state in observations.items():
            if node not in self.nodes or self.nodes[node]["kind"] != "Finding" or state not in {"present", "absent", "unknown"}:
                raise ValueError("Invalid finding or observation state")
        from .ranking import rank_candidates
        return rank_candidates(self, observations, include_draft, limit, patient, category)

    TOOLS = [
        {"name": "search", "description": "Search concepts by Korean or English name; return stable IDs.", "input_schema": {"type": "object", "properties": {"text": {"type": "string"}, "kind": {"type": "string", "enum": sorted(KINDS)}}, "required": ["text"], "additionalProperties": False}},
        {"name": "graph", "description": "Evidence-bearing undirected neighborhood, not causal inference. Drafts excluded by default.", "input_schema": {"type": "object", "properties": {"node": {"type": "string"}, "direction": {"type": "string", "enum": ["in", "out", "both"]}, "depth": {"type": "integer", "minimum": 0, "maximum": 5}, "include_draft": {"type": "boolean"}}, "required": ["node"], "additionalProperties": False}},
        {"name": "rank", "description": "Rank by evidence score, not diagnostic probability. Negative and unknown observations remain separate; age/sex eligibility requires reviewed rules.", "input_schema": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}, "observations": {"type": "object", "additionalProperties": {"type": "string", "enum": ["present", "absent", "unknown"]}}, "include_draft": {"type": "boolean"}, "category": {"type": "string"}, "patient": {"type":"object", "properties":{"age":{"type":"number","minimum":0,"maximum":130},"sex":{"type":"string","enum":["female","male","unknown"]}}, "additionalProperties":False}}, "required": ["observations"], "additionalProperties": False}}
    ]

    def call(self, name, args):
        if name not in {t["name"] for t in self.TOOLS} or not isinstance(args, dict):
            raise ValueError("Invalid tool call")
        return dict(version=self.version, sha256=self.sha256, result=getattr(self, name)(**args))

    def normalize(self, text):
        from .workflow import normalize
        return normalize(self, text)

    def suggest(self, observations, profile='reviewed', patient=None, category=None, limit=5):
        from .workflow import suggest
        return suggest(self, observations, profile, patient, category, limit)

    def guidelines(self, query, limit=3):
        from .guidelines import Guidelines
        from .workflow import resource
        if not isinstance(query,str) or not query.strip() or len(query)>500:
            raise ValueError('Invalid guideline query')
        dictionary,digest=resource('guideline-queries.json')
        expanded=[query]
        for alias,values in dictionary['aliases'].items():
            if alias in query:expanded.extend(values)
        for mention in self.normalize(query)['mentions']:
            expanded.extend(self.nodes[f]['label_en'] for f in mention['candidate_ids'])
        if not hasattr(self,'_guidelines'):
            self._guidelines=Guidelines()
        result=self._guidelines.search(' '.join(dict.fromkeys(expanded))[:500],limit)
        result.update({'original_query':query,'query_alias_sha256':digest,'query_expansion_status':'draft; search terms only, not confirmed diagnosis mappings'})
        return result

    TOOLS += [
        {'name':'guidelines','description':'Retrieve original guideline excerpts with licenses and source URLs from NOVA_GUIDELINES_DIR; titles match is tentative.','input_schema':{'type':'object','properties':{'query':{'type':'string','minLength':1,'maxLength':500},'limit':{'type':'integer','minimum':1,'maximum':10}},'required':['query'],'additionalProperties':False}},
        {'name':'normalize','description':'Propose Korean phrase mappings; user/agent must confirm before observation update.','input_schema':{'type':'object','properties':{'text':{'type':'string','minLength':1,'maxLength':10000}},'required':['text'],'additionalProperties':False}},
        {'name':'suggest','description':'Rank and propose evidence-bearing next questions/exams under an explicit knowledge profile. No diagnostic probabilities.','input_schema':{'type':'object','properties':{'observations':{'type':'object','additionalProperties':{'type':'string','enum':['present','absent','unknown']}},'profile':{'type':'string','enum':['reviewed','pilot','research']},'patient':{'type':'object','properties':{'age':{'type':'number','minimum':0,'maximum':130},'sex':{'type':'string','enum':['female','male','unknown']}},'additionalProperties':False},'category':{'type':'string'},'limit':{'type':'integer','minimum':1,'maximum':20}},'required':['observations'],'additionalProperties':False}}
    ]
