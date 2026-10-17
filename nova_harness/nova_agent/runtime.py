import json
from pathlib import Path

from nova_sdk import NovaError
from . import __version__
from .config import Config
from .protocol import Gateway, seconds_left
from .prompts import STEP, FINAL
from .records import make_record
from .state import PatientState
from .telemetry import Trace
from .validation import action_key, parse_object, validate_action
from .closure import review_closure
from .clinical import ClinicalAdvisor

STOP = {'TURN_LIMIT_REACHED', 'SESSION_EXPIRED', 'SESSION_CLOSED', 'RUN_NOT_ACTIVE', 'LOCAL_DEADLINE'}
REJECTED = {'CONTENT_TOO_LONG', 'EMPTY_CONTENT', 'EXAM_NOT_SPECIFIC', 'EXAM_NOT_RECOGNIZED', 'ACTION_NOT_AVAILABLE'}


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
    state = PatientState(session['initial'], {c['id']: c for c in knowledge['concepts']})
    advisor = ClinicalAdvisor(knowledge['clinical_graph'], str(state.initial.get('opening',''))) if config.meddb else None
    if advisor:
        state.concepts.update({c['id']:c for c in advisor.concepts()})
    initial_server_remaining = int(session['turns_remaining'])
    remaining = min(config.max_turns, initial_server_remaining)
    trace.emit('consult_start', version=__version__, model=config.model, config=vars(config), initial=state.initial)
    feedback, stop_reason = [], 'turn_budget'
    closure_reviewed, closure_missing = False, []
    reserve = config.closing_turns if config.structured_closing else 0
    while remaining > reserve and seconds_left(session) > config.time_margin:
        selected = None
        for _ in range(3):
            clinical = advisor.context(state) if advisor else None
            concepts = list(knowledge['concepts'])
            if clinical:
                concepts += [state.concepts[c] for c in clinical['relevant_concepts'] if c in state.concepts]
            ontology_context = {'concepts': [{k: c[k] for k in ('id', 'label', 'field')} for c in concepts],
                                'relations': knowledge['relations']}
            user = {'patient': state.prompt_snapshot(), 'ontology': ontology_context,
                    'latest_evidence_id': state.evidence[-1].id if state.evidence else None,
                    'turns_remaining_local': remaining, 'seconds_remaining': min(99999, seconds_left(session)),
                    'instruction_feedback': feedback[-3:]}
            if clinical:
                user['clinical_advisor'] = clinical
            if config.structured_closing:
                user['closing_policy'] = '진단·계획·추적·안전·걱정·이해 확인은 별도 마무리 단계에서 수행합니다. 지금은 필요한 문진·진찰을 수행하고 충분하면 DONE. 긴급성은 근거에 맞춰 판단합니다.'
            if closure_missing:
                user['closure_review_missing'] = closure_missing
                user['closure_review_instruction'] = '지적된 누락 중 아직 중요하고 미확인인 항목을 우선 확인합니다. 이미 답을 얻었거나 즉시 이송을 지연하면 반복하지 않습니다.'
            if remaining <= 6:
                user['phase_hint'] = '불필요한 질문을 줄이고 실제 SAY로 판단·계획·경고 증상을 설명한 뒤 마무리하세요.'
            try:
                completion = gateway.chat([{'role': 'system', 'content': STEP},
                                           {'role': 'user', 'content': json.dumps(user, ensure_ascii=False,separators=(',',':'))}])
                choices = completion.get('choices')
                if isinstance(choices, list) and choices and isinstance(choices[0], dict) and choices[0].get('finish_reason') == 'length':
                    trace.emit('output_truncated', stage='planner')
                result = content_of(completion)
                accepted, rejected = state.accept_facts(result.get('facts', []))
                trace.emit('facts_updated', accepted=accepted, rejected=rejected)
                proposal = result.get('next_action', {})
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
            if (config.closure_audit and not closure_reviewed and len(state.evidence) >= 5
                    and remaining > 6 and seconds_left(session) > config.time_margin+180):
                closure_reviewed = True  # once, even on invalid/failed review; never loop indefinitely
                try:
                    audit = review_closure(gateway, state, result.get('hypotheses', []))
                    trace.emit('closure_review', review=audit)
                    if not audit['ready'] and not audit['urgent_exit']:
                        proposal = audit['next_action']
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
    if stop_reason in {'SESSION_CLOSED', 'SESSION_EXPIRED', 'RUN_NOT_ACTIVE', 'LOCAL_DEADLINE'}:
        raise NovaError(stop_reason)
    proposed = {}
    if advisor:
        trace.emit('clinical_state', context=advisor.context(state))
    for _ in range(2):
        try:
            payload = {'patient':state.prompt_snapshot(),'clinical_advisor':advisor.context(state) if advisor else None}
            proposed = content_of(gateway.chat([{'role': 'system', 'content': FINAL},
                                               {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}], final=True))
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
    trace.emit('record_ready', note=note, diagnosis=diagnosis, fallback=not bool(proposed))
    result = gateway.invoke('diagnose', note=note, diagnosis=diagnosis, final=True)
    trace.emit('consult_complete', result=result, diagnosis=diagnosis,
               model_calls=len(gateway.chat_ids), input_tokens=gateway.input_tokens,
               output_tokens=gateway.output_tokens)
    return result
