import json
import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from .kcd import KCD, DEFAULT_KCD

WEB = Path(__file__).resolve().parents[1] / "web" / "index.html"

def serve(kb, port=8765):
    snapshot = gzip.compress(json.dumps(dict(**kb.data, sha256=kb.sha256), ensure_ascii=False, separators=(",", ":")).encode())
    kcd = KCD() if DEFAULT_KCD.exists() else None
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            query = urlparse(self.path)
            args = parse_qs(query.query)
            try:
                if query.path == "/":
                    payload, mime = WEB.read_bytes(), "text/html; charset=utf-8"
                elif query.path == '/api/health':
                    payload, mime = json.dumps({'service':'nova-meddb','status':'ready','version':kb.version}).encode(), 'application/json; charset=utf-8'
                elif query.path in {"/app.css", "/app.js", "/agent-ui.js"}:
                    file = WEB.parent / query.path[1:]
                    payload = file.read_bytes()
                    mime = "text/css; charset=utf-8" if file.suffix == ".css" else "application/javascript; charset=utf-8"
                elif query.path == "/api/data":
                    payload, mime = snapshot, "application/json; charset=utf-8"
                elif query.path.startswith('/api/kcd'):
                    if kcd is None:
                        self.send_error(503, 'Local HIRA KCD snapshot not installed')
                        return
                    if query.path == '/api/kcd':
                        result = kcd.search(args.get('q',[''])[0], int(args.get('offset',['0'])[0]), int(args.get('limit',['50'])[0]))
                    elif query.path == '/api/kcd/code':
                        result = kcd.code(args.get('code',[''])[0])
                    elif query.path == '/api/kcd/mappings':
                        concept = kb.nodes.get(args.get('concept',[''])[0])
                        if not concept or concept['kind'] != 'Disease':
                            raise ValueError('Disease concept required')
                        result = kcd.candidates(concept)
                    else:
                        self.send_error(404)
                        return
                    payload, mime = json.dumps(result, ensure_ascii=False).encode(), 'application/json; charset=utf-8'
                elif query.path == "/api/search":
                    payload, mime = json.dumps(kb.search(args.get("q", [""])[0]), ensure_ascii=False).encode(), "application/json; charset=utf-8"
                elif query.path == "/api/graph":
                    payload, mime = json.dumps(kb.graph(args.get("node", [""])[0], args.get("draft", ["false"])[0] == "true", int(args.get("depth", ["2"])[0]), args.get("direction", ["both"])[0], None if args.get("source",["all"])[0]=="all" else args["source"][0]), ensure_ascii=False).encode(), "application/json; charset=utf-8"
                else:
                    self.send_error(404)
                    return
            except ValueError as exc:
                self.send_error(400, str(exc))
                return
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header('Cache-Control','no-store')
            if query.path == "/api/data": self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        def do_POST(self):
            if self.path not in {"/api/rank", "/api/normalize", "/api/suggest", "/api/guidelines"}:
                self.send_error(404)
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 65536:
                    raise ValueError("Invalid body size")
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict) or not isinstance(body.get("include_draft", False), bool):
                    raise ValueError("Invalid request")
                if self.path == '/api/guidelines':
                    result = kb.guidelines(body.get('query'),body.get('limit',3))
                elif self.path == '/api/normalize':
                    result = kb.normalize(body.get('text'))
                elif self.path == '/api/suggest':
                    result = kb.suggest(body.get('observations', {}), body.get('profile','reviewed'),body.get('patient'),body.get('category'),body.get('limit',5))
                else:
                    result = kb.rank(body.get("observations", {}), body.get("include_draft", False), body.get("limit", 30), body.get("patient"), body.get("category"))
            except (ValueError, TypeError) as exc:
                self.send_error(400, str(exc))
                return
            payload = json.dumps(result, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    address = getattr(server,'server_address',('127.0.0.1',port))
    print(f"MedDB: http://{address[0]}:{address[1]}", flush=True)
    server.serve_forever()
