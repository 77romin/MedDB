"""B1 policy and closing with a conservative, source-preserving Q/A reader."""
from examples import agent_b1, reader_b1_observed


def consult(client, db, fallback=None, **kwargs):
    return agent_b1.consult(client, db, fallback=fallback, reader=reader_b1_observed, **kwargs)
