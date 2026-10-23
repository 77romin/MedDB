"""Reversible E2 overlay that keeps ontology summaries without raw Q/A append."""


def install():
    import meddb.coverage as coverage

    original = coverage.CareCoverage

    class ConceptCompactCoverage(original):
        def append_record(self, note):
            # The upstream record writer already receives the full transcript and
            # ontology draft. Re-appending raw Q/A here duplicates the same facts,
            # inflates HPI/PMH/FH, and hides the concise clinical concepts.
            return None

    coverage.CareCoverage = ConceptCompactCoverage
    return original


def restore(original):
    import meddb.coverage as coverage
    coverage.CareCoverage = original
