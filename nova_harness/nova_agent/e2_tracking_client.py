"""Transparent client proxy that captures E2 evidence and audits final SOAP."""
from .e2_soap_audit import audit, require_complete
from .e2_soap_router import reconcile


class TrackingClient:
    def __init__(self, client, ledger):
        self._client = client
        self.ledger = ledger
        self.last_audit = None

    def __getattr__(self, name):
        return getattr(self._client, name)

    def say(self, content, **kwargs):
        try:
            reply = self._client.say(content, **kwargs)
        except Exception as exc:
            self.ledger.record_error("SAY", content, getattr(exc, "code", type(exc).__name__))
            raise
        self.ledger.record("SAY", content, reply)
        return reply

    def exam(self, content, **kwargs):
        try:
            reply = self._client.exam(content, **kwargs)
        except Exception as exc:
            self.ledger.record_error("EXAM", content, getattr(exc, "code", type(exc).__name__))
            raise
        self.ledger.record("EXAM", content, reply)
        return reply

    def diagnose(self, *, note, diagnosis, **kwargs):
        repaired = reconcile(note, self.ledger)
        self.last_audit = audit(repaired, self.ledger)
        require_complete(self.last_audit)
        return self._client.diagnose(note=repaired, diagnosis=diagnosis, **kwargs)
