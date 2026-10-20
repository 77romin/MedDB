"""Replay one completed E2 trace and compare upstream with convergence shadow.

Uses only saved API responses.  It performs no network or model calls and emits
only aggregate equality results, never the clinical transcript.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor/meddb"))

from examples.hybrid_care import consult, prepare
from nova_agent.e2_convergence_shadow import install, restore


def _load(trace):
    rows = [json.loads(line) for line in Path(trace).read_text(encoding="utf-8").splitlines()]
    responses = {row.get("request_id"): row.get("response") for row in rows if row.get("event") == "http_response"}
    session = next(
        (row.get("response") for row in rows if row.get("event") == "http_response"
         and isinstance(row.get("response"), dict) and row["response"].get("initial")), None
    )
    calls = []
    for row in rows:
        if row.get("event") != "http_request":
            continue
        body = row.get("body") or {}
        response = responses.get(body.get("request_id"))
        if row.get("path") == "/v1/chat/completions":
            calls.append({"kind": "chat", "messages": body.get("messages"),
                          "max_tokens": body.get("max_tokens"), "response": response})
        elif row.get("path", "").endswith("/actions"):
            calls.append({"kind": str(body.get("action", "")).lower(), "content": body.get("content"),
                          "note": body.get("note"), "diagnosis": body.get("diagnosis"), "response": response})
    if not session or not calls:
        raise ValueError("trace must contain a completed E2 session")
    return session, calls


class ReplayClient:
    def __init__(self, session, calls):
        self._session = deepcopy(session)
        self._session["deadline"] = "2099-01-01T00:00:00+00:00"
        self._calls = deepcopy(calls)
        self.seen = []

    def session(self):
        return deepcopy(self._session)

    def _pop(self, kind):
        if not self._calls:
            raise AssertionError(f"unexpected {kind}: replay exhausted")
        row = self._calls.pop(0)
        if row["kind"] != kind:
            raise AssertionError(f"expected {row['kind']}, got {kind}")
        return row

    def chat(self, messages, max_tokens):
        row = self._pop("chat")
        if row["messages"] != messages or row["max_tokens"] != max_tokens:
            raise AssertionError("chat request differs from recorded E2 request")
        self.seen.append(("chat", max_tokens))
        return deepcopy(row["response"])

    def say(self, content):
        row = self._pop("say")
        if row["content"] != content:
            raise AssertionError("SAY content differs from recorded E2 request")
        self.seen.append(("say", content))
        return deepcopy(row["response"])

    def exam(self, content):
        row = self._pop("exam")
        if row["content"] != content:
            raise AssertionError("EXAM content differs from recorded E2 request")
        self.seen.append(("exam", content))
        return deepcopy(row["response"])

    def diagnose(self, note, diagnosis):
        row = self._pop("diagnose")
        self.seen.append(("diagnose", diagnosis, json.dumps(note, ensure_ascii=False, sort_keys=True)))
        return deepcopy(row["response"])

    @property
    def remaining(self):
        return len(self._calls)


def _run(session, calls, shadow):
    client = ReplayClient(session, calls)
    original = install() if shadow else None
    try:
        outcome = consult(client, prepare(), knowledge_mode="clinical", reference_profile="reviewed")
    finally:
        if original is not None:
            restore(original)
    return outcome, client.seen, client.remaining


def compare(trace):
    session, calls = _load(trace)
    upstream, upstream_seen, upstream_remaining = _run(session, calls, False)
    shadow, shadow_seen, shadow_remaining = _run(session, calls, True)
    return {
        "trace": str(Path(trace)),
        "recorded_calls": len(calls),
        "upstream_consumed_all": upstream_remaining == 0,
        "shadow_consumed_all": shadow_remaining == 0,
        "actions_identical": upstream_seen == shadow_seen,
        "outcome_identical": upstream == shadow,
        "diagnosis": shadow_seen[-1][1] if shadow_seen and shadow_seen[-1][0] == "diagnose" else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("traces", nargs="+")
    parser.add_argument("--out")
    args = parser.parse_args()
    result = [compare(path) for path in args.traces]
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
