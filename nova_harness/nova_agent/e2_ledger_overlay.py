"""Reversible ledger-only overlay for upstream E2; clinical actions stay unchanged."""
from contextvars import ContextVar

from .e2_evidence_ledger import EvidenceLedger
from .e2_tracking_client import TrackingClient

ACTIVE_LEDGER = ContextVar("e2_active_ledger", default=None)
LAST_RUN = None


def install():
    from examples import hybrid_care
    import meddb.coverage as coverage

    original_consult = hybrid_care.base_consult
    original_coverage = coverage.CareCoverage

    class AnnotatingCoverage(original_coverage):
        def observe(self, target, question, answer, turn):
            super().observe(target, question, answer, turn)
            ledger = ACTIVE_LEDGER.get()
            if ledger is not None and target:
                field = self.extra.get(target, (None, ""))[1] if target in self.extra else ""
                ledger.annotate(turn, question, target, field)

    def ledger_consult(client, *args, **kwargs):
        global LAST_RUN
        ledger = EvidenceLedger()
        token = ACTIVE_LEDGER.set(ledger)
        tracked = TrackingClient(client, ledger)
        try:
            return original_consult(tracked, *args, **kwargs)
        finally:
            LAST_RUN = {"ledger": ledger.snapshot(), "audit": tracked.last_audit}
            ACTIVE_LEDGER.reset(token)

    coverage.CareCoverage = AnnotatingCoverage
    hybrid_care.base_consult = ledger_consult
    return original_consult, original_coverage


def restore(original):
    from examples import hybrid_care
    import meddb.coverage as coverage
    original_consult, original_coverage = original
    hybrid_care.base_consult = original_consult
    coverage.CareCoverage = original_coverage
