"""Coverage and communication candidate; clinical completeness is not a promised score."""
from examples.hybrid_comm import prepare
from examples.hybrid_comm import consult as base_consult


def consult(client, db, fallback=None, knowledge_mode=None, reference_profile=None):
    return base_consult(client, db, fallback, knowledge_mode, reference_profile, coverage=True)
