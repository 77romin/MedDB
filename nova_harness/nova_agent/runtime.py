import json
from pathlib import Path

from nova_sdk import NovaError
from . import __version__
from .config import Config
from .protocol import Gateway, seconds_left
from .prompts import STEP, FINAL
from .records import make_record, normalize_assessment
from .state import PatientState
from .telemetry import Trace
from .validation import action_key, parse_object, validate_action
from .closure import review_closure
from .clinical import ClinicalAdvisor
from .coverage import CoveragePlanner
from .goals import DecisionGoals
from .decision_axes import decision_axes

STOP = {'TURN_LIMIT_REACHED', 'SESSION_EXPIRED', 'SESSION_CLOSED', 'RUN_NOT_ACTIVE', 'LOCAL_DEADLINE'}
REJECTED = {'CONTENT_TOO_LONG', 'EMPTY_CONTENT', 'EXAM_NOT_SPECIFIC', 'EXAM_NOT_RECOGNIZED', 'ACTION_NOT_AVAILABLE'}


def collection_phase_hint(remaining, reserve):
    if remaining <= reserve + 5:
        return ('수집 마무리 구간입니다. 같은 보조 영역을 세분해 반복하지 말고 '
                '아직 진단·안전·치료를 바꿀 서로 다른 핵심 범위를 우선하세요.')
    return None


def prepare():
    # Deliberately never load sample scripts, answer keys, or data from previous encounters.
    knowledge = json.loads(Path(__file__).with_name('ontology.json').read_text(encoding='utf-8'))
    knowledge['clinical_graph'] = json.loads(Path(__file__).with_name('clinical_graph.json').read_text(encoding='utf-8'))
    return knowledge


def content_of(completion):
    try:
        value = completion['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError):
        raise ValueError('missing completion content')
    return parse_object(value)


def consult(client, knowledge, config=None, trace=None):
    config, trace = config or Config(), trace or getattr(client, 'trace', Trace())
    gateway = Gateway(client, config, trace)
    session = client.session()
    gateway.deadline = session.get('deadline')
    state = PatientState(session['initial'], {c['id']: c for c in knowledge['concepts']}, compact_context=config.compact_context)
    advisor = ClinicalAdvisor(knowledge['clinical_graph'], str(state.initial.get('opening',''))) if config.meddb else None
    if advisor:
        state.concepts.update({c['id']:c for c in advisor.concepts()})
    coverage = CoveragePlanner(advisor, state) if advisor and config.coverage else None
    goals = DecisionGoals(state) if config.decision_review else None
    initial_server_remaining = int(session['turns_remaining'])
    remaining = min(config.max_turns, initial_server_remaining)
    trace.emit('consult_start', version=__version__, model=config.model, config=vars(config), initial=state.initial)
    feedback, stop_reason = [], 'turn_budget'
    closure_reviews, closure_missing = 0, []
    reserve = config.closing_turns if config.structured_closing else 0
    planner_tokens = config.step_tokens
    while remaining > reserve and seconds_left(session) > config.time_margin:
        selected = None
        retry_tokens = planner_tokens
        for _ in range(3):
            clinical = advisor.context(state) if advisor else None
            concepts = list(knowledge['concepts'])
            if clinical:
                concepts += [state.concepts[c] for c in clinical['relevant_concepts'] if c in state.concepts]
            if coverage and state.evidence:
                latest_target = state.evidence[-1].target
                concepts += [c for c in state.concepts.values() if c['id'] == latest_target or c.get('exam_target') == latest_target]
            concepts = list({c['id']:c for c in concepts}.values())
            ontology_context = {'concepts': [{k:c[k] for k in ('id','label','field','kind','exam_target') if c.get(k) is not None} for c in concepts],
                                'relations': knowledge['relations']}
            user = {'patient': state.prompt_snapshot([c['id'] for c in concepts]), 'ontology': ontology_context,
                    'latest_evidence_id': state.evidence[-1].id if state.evidence else None,
                    'turns_remaining_local': remaining, 'seconds_remaining': min(99999, seconds_left(session)),
                    'instruction_feedback': feedback[-3:]}
            if clinical:
                user['clinical_advisor'] = clinical
            axes = decision_axes(state, clinical)
            if axes:
                user['decision_axes'] = axes
            if coverage:
                user['collection_coverage'] = coverage.snapshot(compact=True)
            if goals:
                user['patient'].pop('decision_goals', None)
                user['decision_goals'] = goals.snapshot()
            if config.structured_closing:
                user['closing_policy'] = '일반 설명은 별도 마무리 단계에서 수행합니다. 지금 필요한 안전 행동은 마무리까지 기다리지 말고 실제 SAY로 안내합니다. 필요한 문진·진찰이 충분하면 DONE이며 긴급 대응을 지연하지 않습니다.'
            if closure_missing:
                user['closure_review_missing'] = closure_missing
                user['closure_review_instruction'] = '지적된 누락 중 아직 중요하고 미확인인 항목을 우선 확인합니다. 이미 답을 얻었거나 즉시 이송을 지연하면 반복하지 않습니다.'
            phase_hint = collection_phase_hint(remaining, reserve)
            if phase_hint:
                user['phase_hint'] = phase_hint
            try:
                completion = gateway.chat([{'role': 'system', 'content': STEP},
                                           {'role': 'user', 'content': json.dumps(user, ensure_ascii=False,separators=(',',':'))}],
                                           max_tokens=retry_tokens)
                choices = completion.get('choices')
                if isinstance(choices, list) and choices and isinstance(choices[0], dict) and choices[0].get('finish_reason') == 'length':
                    trace.emit('output_truncated', stage='planner')
                    planner_tokens = max(config.step_tokens, 3072)
                    retry_tokens = planner_tokens
                result = content_of(completion)
                accepted, rejected = state.accept_facts(result.get('facts', []))
                trace.emit('facts_updated', accepted=accepted, rejected=rejected)
                if goals:
                    accepted_goals, rejected_goals = goals.update(result.get('goal_updates', []))
                    trace.emit('decision_goals_updated', accepted=accepted_goals, rejected=rejected_goals)
                    feedback.extend(rejected_goals[-1:])
                proposal = result.get('next_action', {})
                if coverage:
                    coverage.accept_initial(result.get('initial_coverage', []))
                    proposal, override = coverage.choose(proposal, remaining, reserve)
                    if override: trace.emit('coverage_override', **override)
                action, text = validate_action(proposal, state.seen)
                if action == 'DONE' and not config.structured_closing and not state.communication.intersection({'plan', 'safety_net'}) and remaining > 2:
                    raise ValueError('DONE before sending patient plan/safety-net SAY; explain if clinically possible')
                selected = action, text, proposal
                trace.emit('action_selected', action=action, content=text, purpose=proposal.get('purpose'),
                           hypotheses=result.get('hypotheses', []), remaining=remaining)
                break
            except (ValueError, TypeError) as exc:
                feedback.append(str(exc)); trace.emit('validation_error', stage='planner', reason=str(exc))
            except NovaError as exc:
                stop_reason = exc.code
                trace.emit('planner_stopped', code=exc.code)
                break
        if selected is None:
            stop_reason = stop_reason if stop_reason != 'turn_budget' else 'planner_failed'
            break
        action, text, proposal = selected
        if action == 'DONE':
            urgent = (proposal.get('urgent_exit') is True
                      and isinstance(proposal.get('urgent_reason'), str) and bool(proposal['urgent_reason'].strip())
                      and isinstance(proposal.get('urgency_evidence_ids'), list) and bool(proposal['urgency_evidence_ids'])
                      and all(eid in {'initial'} | {e.id for e in state.evidence}
                              for eid in proposal['urgency_evidence_ids'] if isinstance(eid, str))
                      and all(isinstance(eid, str) for eid in proposal['urgency_evidence_ids']))
            if urgent:
                stop_reason = 'urgent_exit_source_checked'; break
            review_limit = config.closure_review_limit if goals is not None else 1
            if ((config.closure_audit or goals is not None) and closure_reviews < review_limit
                    and len(state.evidence) >= (3 if goals else 5)
                    and remaining > max(6, reserve+1) and seconds_left(session) > config.time_margin+180):
                closure_reviews += 1  # bounded even on invalid/failed review
                try:
                    audit = review_closure(
                        gateway, state, result.get('hypotheses', []), goals.snapshot() if goals else None,
                        decision_axes(state, clinical), coverage.snapshot(compact=True) if coverage else None)
                    trace.emit('closure_review', review=audit)
                    if not audit['ready'] and not audit['urgent_exit']:
                        proposal = audit['next_action']
                        if coverage:
                            proposal, _ = coverage.choose(proposal, remaining, reserve)
                        action, text = validate_action(proposal, state.seen)
                        closure_missing = audit['missing']
                        trace.emit('closure_followup', action=action, content=text, missing=closure_missing)
                    else:
                        stop_reason = 'urgent_exit' if audit['urgent_exit'] else 'reviewed_done'
                        break
                except (ValueError, TypeError, NovaError) as exc:
                    trace.emit('closure_review_unavailable', reason=getattr(exc, 'code', str(exc)))
                    stop_reason = 'doctor_done_review_unavailable'; break
            else:
                stop_reason = 'doctor_done'; break
        state.seen.add(action_key(action, text))
        try:
            reply = gateway.invoke('say' if action == 'SAY' else 'exam', text)
            targets = {a['target']:a for a in clinical['actions']} if clinical else {}
            target = proposal.get('target', '')
            if target not in targets or action_key(action,text) != action_key(targets[target]['type'],targets[target]['content']):
                target = ''
            if coverage:
                target = coverage.target_for(action, text) or target
            tags = proposal.get('communication', [])
            evidence = state.add_response(action, text, reply, target, communication=tags)
            server_remaining = int(reply.get('turns_remaining', initial_server_remaining-state.turns_used))
            remaining = max(0, min(remaining-1, config.max_turns-(initial_server_remaining-server_remaining), server_remaining))
            trace.emit('evidence_added', evidence=vars(evidence), remaining=remaining)
        except NovaError as exc:
            state.errors.append({'action': action, 'content': text, 'code': exc.code})
            if exc.code in REJECTED:
                # SDK errors discard the response body: ask the server for authoritative remaining turns.
                try:
                    refreshed = client.session()
                    server_remaining = int(refreshed['turns_remaining'])
                    remaining = max(0, min(config.max_turns-(initial_server_remaining-server_remaining), server_remaining))
                    state.turns_used = initial_server_remaining-server_remaining
                except (NovaError, KeyError, TypeError, ValueError):
                    stop_reason = 'cannot_resync_after_rejection'; break
                feedback.append(exc.code+': 하나의 구체적인 항목으로 바꾸고 같은 요청을 반복하지 마세요.')
                trace.emit('turns_resynced', remaining=remaining, code=exc.code)
                continue
            stop_reason = exc.code; break
    if seconds_left(session) <= config.time_margin:
        stop_reason = 'time_margin'
    trace.emit('collection_finished', reason=stop_reason, state=state.snapshot(), remaining=remaining)
    if coverage:
        trace.emit('coverage_finished', coverage=coverage.snapshot(), reason=stop_reason)
    if stop_reason in {'SESSION_CLOSED', 'SESSION_EXPIRED', 'RUN_NOT_ACTIVE', 'LOCAL_DEADLINE'}:
        raise NovaError(stop_reason)
    proposed = {}
    if advisor:
        trace.emit('clinical_state', context=advisor.context(state))
    guideline_context = None
    if config.guidelines:
        from .guidelines import Guidelines
        try:
            hypotheses = advisor.context(state)['hypotheses'] if advisor else []
            terms = [advisor.diseases[h['id']].get('en','') for h in hypotheses[:2]] if advisor else []
            query = ' '.join(terms) or str(state.initial.get('opening',''))[:200]
            guideline_context = Guidelines().search(query[:500],limit=2)
            trace.emit('guideline_retrieval', result=guideline_context)
        except (OSError,ValueError,UnicodeError) as exc:
            trace.emit('guideline_unavailable', exception=type(exc).__name__)
    for _ in range(2):
        try:
            payload = {'patient':state.prompt_snapshot(),'clinical_advisor':advisor.context(state) if advisor else None}
            if guideline_context:
                payload['guideline_references'] = guideline_context
            proposed = normalize_assessment(content_of(gateway.chat([{'role': 'system', 'content': FINAL},
                                               {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}], final=True)))
            note, diagnosis = make_record(state, proposed)
            break
        except (ValueError, TypeError) as exc:
            trace.emit('validation_error', stage='record', reason=str(exc))
            proposed = {}
        except NovaError as exc:
            trace.emit('record_model_error', code=exc.code); proposed = {}; break
    else:
        proposed = {}
    if config.structured_closing and remaining > 0:
        from .closing import close_consultation
        # An early DONE must not spend every unused collection turn repeating explanations.
        allowance = min(remaining, config.closing_turns)
        unspent_collection = remaining-allowance
        trace.emit('closing_budget', allowance=allowance, unspent_collection=unspent_collection)
        proposed, closing_left = close_consultation(gateway, state, proposed, allowance, trace, advisor)
        remaining = unspent_collection+closing_left
    note, diagnosis = make_record(state, proposed)
    from .history import history_routes
    trace.emit('record_evidence_audit', state=state.snapshot(), history_routes=history_routes(state, proposed))
    trace.emit('record_ready', note=note, diagnosis=diagnosis, fallback=not bool(proposed))
    result = gateway.invoke('diagnose', note=note, diagnosis=diagnosis, final=True)
    trace.emit('consult_complete', result=result, diagnosis=diagnosis,
               model_calls=len(gateway.chat_ids), input_tokens=gateway.input_tokens,
               output_tokens=gateway.output_tokens)
    return result
