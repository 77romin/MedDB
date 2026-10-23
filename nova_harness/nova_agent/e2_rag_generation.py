"""R3c retains R3b query/selection and changes only the record generation role."""
from . import e2_rag_query
from .rag_generation import GenerationClient

LAST_RUN=None


def install(store):
    global LAST_RUN
    from examples import hybrid_agent as H
    original=e2_rag_query.install(store)
    query_writer=H.write_record
    events=[]
    LAST_RUN={'events':[]}

    def write_record(client,db,kb,opening,vitals,transcript,contextual_plan=False):
        global LAST_RUN
        try:
            return query_writer(GenerationClient(client,events),db,kb,opening,vitals,transcript,contextual_plan)
        finally:LAST_RUN={'events':list(events)}

    H.write_record=write_record
    return original


def restore(original):e2_rag_query.restore(original)
