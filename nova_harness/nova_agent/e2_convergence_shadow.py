"""Reversible E2 shadow overlay; records convergence without changing actions."""
from .e2_convergence import ConvergenceEngine

LAST_RUN = None


def install():
    import meddb.coverage as coverage

    original = coverage.CareCoverage

    class ShadowCoverage(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._convergence = ConvergenceEngine(self.db, self.complaint)

        def needed(self, kb):
            global LAST_RUN
            actions = super().needed(kb)
            self._convergence.observe(kb, actions, self.records)
            LAST_RUN = {"mode": "shadow", "trajectory": self._convergence.snapshot()}
            return actions

        def trace(self):
            trace = super().trace()
            trace["convergence"] = self._convergence.snapshot()
            return trace

    coverage.CareCoverage = ShadowCoverage
    return original


def restore(original):
    import meddb.coverage as coverage
    coverage.CareCoverage = original
