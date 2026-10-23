"""R4: local LangGraph orchestration of the same R3c business operations."""
import sqlite3
from typing import Any, TypedDict

from . import e2_rag, e2_rag_query, e2_rag_selection, e2_rag_generation
from .rag_query import QueryStore
from .rag_selector import SelectorStore, observations
from .rag_generation import GenerationClient

LAST_RUN=None


class WorkflowState(TypedDict, total=False):
    args: Any
    client: Any
    evidence: list
    query: str
    candidates: list
    selected: list
    result: Any
    nodes: list
    audit: dict


class FixedDocuments:
    def __init__(self):self.documents=[]
    def search(self,query,k=2):return self.documents


def prepare_threaded_reads(store):
    """Only the FTS connection changes: same rows/scoring, read-only graph usage.

    LangGraph may run a sequential node in a worker thread. Rebuild the small
    metadata FTS connection with cross-thread reads enabled; no algorithm change.
    """
    if getattr(store,'fts',False) and hasattr(store,'metadata'):
        connection=sqlite3.connect(':memory:',check_same_thread=False)
        connection.execute('create virtual table titles using fts5(title,heading)')
        connection.executemany('insert into titles(rowid,title,heading) values(?,?,?)',
                               [(i+1,m['title'],m.get('heading','')) for i,m in enumerate(store.metadata)])
        store.lexical.close();store.lexical=connection


def validate_runtime():
    from langgraph.graph import StateGraph, START, END
    graph=StateGraph(WorkflowState)
    graph.add_node('validate',lambda state:{})
    graph.add_edge(START,'validate');graph.add_edge('validate',END)
    return graph.compile(checkpointer=None)


def install(store):
    global LAST_RUN
    from examples import hybrid_agent as H
    from langgraph.graph import StateGraph, START, END
    from langsmith import tracing_context
    prepare_threaded_reads(store)
    planned=QueryStore(store)
    candidates_store=FixedDocuments();selected_store=FixedDocuments()
    filtered=SelectorStore(candidates_store)
    # Capture the existing source-injection writer once, with the original E2
    # writer as its fallback. No global function changes happen inside nodes.
    original=e2_rag.install(selected_store)
    record_writer=H.write_record
    H.write_record=original
    generation_events=[]
    LAST_RUN={'nodes':[]}

    def context(state):
        client,db,kb,opening,vitals,transcript,_=state['args']
        terms=[]
        for candidate in (kb.ranked(k=2) if kb.complaint else []):
            item=db.diseases.get(candidate['id'],{})
            terms.extend(str(item.get(key,'')) for key in ('ko','en'))
        return {'client':GenerationClient(client,generation_events),
                'evidence':observations(opening,vitals,transcript),'query':' '.join(terms).strip(),
                'selected':[],'candidates':[],'nodes':['context']}

    def retrieve(state):
        documents=[]
        if state['query']:
            planned.context=(state['client'],state['evidence'])
            try:documents=planned.search(state['query'],k=2)
            except (OSError,ValueError,RuntimeError):documents=[]
        return {'candidates':documents,'nodes':state['nodes']+['plan_and_retrieve']}

    def select(state):
        candidates_store.documents=state['candidates']
        filtered.context=(state['client'],state['evidence'])
        try:documents=filtered.search(state['query'],k=2)
        except (OSError,ValueError,RuntimeError):documents=[]
        return {'selected':documents,'nodes':state['nodes']+['select']}

    def generate(state):
        selected_store.documents=state['selected']
        args=list(state['args']);args[0]=state['client']
        result=record_writer(*args)
        return {'result':result,'nodes':state['nodes']+['generate']}

    def audit(state):
        # Inspect rather than silently edit or regenerate the submitted record.
        note,diagnosis=state['result']
        allowed={d['chunk_id'] for d in state['selected']}
        source_audit=e2_rag.LAST_RUN or {}
        cited=set(source_audit.get('cited_chunk_ids',[]))
        invalid=set(source_audit.get('invalid_citation_ids',[])) | (cited-allowed)
        result={'has_soap':isinstance(note,dict) and all(k in note for k in ('S','O','A','P')),
                'has_diagnosis':bool(str(diagnosis).strip()),'selected_count':len(allowed),
                'unverified_citation_ids':sorted(invalid)}
        return {'audit':result,'nodes':state['nodes']+['audit']}

    graph=StateGraph(WorkflowState)
    for name,node in (('context',context),('plan_and_retrieve',retrieve),('select',select),('generate',generate),('audit',audit)):
        graph.add_node(name,node)
    graph.add_edge(START,'context');graph.add_edge('context','plan_and_retrieve')
    graph.add_conditional_edges('plan_and_retrieve',lambda state:'select' if state['candidates'] else 'generate',
                                {'select':'select','generate':'generate'})
    graph.add_edge('select','generate');graph.add_edge('generate','audit');graph.add_edge('audit',END)
    compiled=graph.compile(checkpointer=None)

    def write_record(client,db,kb,opening,vitals,transcript,contextual_plan=False):
        global LAST_RUN
        try:
            # No external tracing, remote graph server, checkpoint persistence,
            # parallel clinical execution, graph retry, or graph-wide rerun.
            with tracing_context(enabled=False):
                state=compiled.invoke({'args':(client,db,kb,opening,vitals,transcript,contextual_plan)},
                                      config={'recursion_limit':8,'max_concurrency':1})
            LAST_RUN={'nodes':state['nodes'],'selected_ids':[d['chunk_id'] for d in state['selected']],
                      'audit':state['audit']}
            return state['result']
        finally:
            planned.context=None;filtered.context=None
            e2_rag_query.LAST_RUN={'attempts':planned.attempts,'events':list(planned.events)}
            e2_rag_selection.LAST_RUN={'attempts':filtered.attempts,'events':list(filtered.events)}
            e2_rag_generation.LAST_RUN={'events':list(generation_events)}

    H.write_record=write_record
    return original


def restore(original):e2_rag.restore(original)
