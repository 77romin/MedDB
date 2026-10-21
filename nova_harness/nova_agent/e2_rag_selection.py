"""R3a wrapper: same R2 retrieval and R1 generation, one new selector role."""
from . import e2_rag
from .rag_selector import SelectorStore, observations

LAST_RUN=None


def install(store):
    global LAST_RUN
    from examples import hybrid_agent as H
    filtered=SelectorStore(store)
    original=e2_rag.install(filtered)
    rag_writer=H.write_record
    LAST_RUN={'attempts':0,'events':[]}

    def write_record(client,db,kb,opening,vitals,transcript,contextual_plan=False):
        global LAST_RUN
        filtered.context=(client,observations(opening,vitals,transcript))
        try:
            return rag_writer(client,db,kb,opening,vitals,transcript,contextual_plan)
        finally:
            filtered.context=None
            LAST_RUN={'attempts':filtered.attempts,'events':list(filtered.events)}

    H.write_record=write_record
    return original


def restore(original):
    e2_rag.restore(original)
