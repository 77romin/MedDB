"""R3b layers query planning before the unchanged R3a suitability selector."""
from . import e2_rag_selection
from .rag_selector import observations
from .rag_query import QueryStore

LAST_RUN=None


def install(store):
    global LAST_RUN
    from examples import hybrid_agent as H
    planned=QueryStore(store)
    original=e2_rag_selection.install(planned)
    selected_writer=H.write_record
    LAST_RUN={'attempts':0,'events':[]}

    def write_record(client,db,kb,opening,vitals,transcript,contextual_plan=False):
        global LAST_RUN
        planned.context=(client,observations(opening,vitals,transcript))
        try:
            return selected_writer(client,db,kb,opening,vitals,transcript,contextual_plan)
        finally:
            planned.context=None
            LAST_RUN={'attempts':planned.attempts,'events':list(planned.events)}

    H.write_record=write_record
    return original


def restore(original):
    e2_rag_selection.restore(original)
