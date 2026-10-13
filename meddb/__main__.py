import sys
if len(sys.argv) > 1 and sys.argv[1] == "clinical":
    from .clinical_cli import main
    raise SystemExit(main(sys.argv[2:]))

import argparse
import json
from .kb import KB

parser = argparse.ArgumentParser()
parser.add_argument("command", choices=["validate", "search", "graph", "rank", "serve", "export-rdf", "validate-rdf"])
parser.add_argument("value", nargs="?", default="")
parser.add_argument("--include-draft", action="store_true")
parser.add_argument("--port", type=int, default=8765)
parser.add_argument("--version")
parser.add_argument("--node")
args = parser.parse_args()
kb = KB(version=args.version)
if args.command == "serve":
    from .server import serve
    serve(kb, args.port)
elif args.command == "validate-rdf":
    from .validation import validate_rdf
    result = validate_rdf(kb, args.include_draft, args.node)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['conforms'] else 1)
elif args.command == "export-rdf":
    from .rdf import export
    print(export(kb, args.include_draft), end="")
else:
    if args.command == "validate":
        result = dict(valid=True, version=kb.version, sha256=kb.sha256, concepts=len(kb.nodes), assertions=len(kb.data["assertions"]))
    elif args.command == "search":
        result = kb.search(args.value)
    elif args.command == "graph":
        result = kb.graph(args.value, args.include_draft)
    else:
        result = kb.rank(json.loads(args.value), args.include_draft)
    print(json.dumps(result, ensure_ascii=False, indent=2))
