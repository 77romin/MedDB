"""Patch E2 to answer a question raised during its closing sentences."""
import types
from pathlib import Path

OLD = '''    said: list[str] = []
    if room():
        for sentence in _closing_sentences(client, db, note, diagnosis, concern, comprehensive=bool(care)):
            if not room():
                break
            try:
                say(sentence)
                said.append(sentence)
            except NovaError as exc:
                st["stopped"] = getattr(exc, "code", "") in STOP_CODES
                break
        if room(2):
            try:
                reply = say(QUESTIONS_Q)
                if QUESTION_CUE.search(reply or "") and not NO_QUESTION.search(_nfc(reply)):
                    answer = _answer_question(client, note, diagnosis, reply)
                    if room():
                        say(answer)
                        said.append(answer)
            except NovaError:
                pass
'''

NEW = '''    said: list[str] = []
    pending_question = ""
    if room():
        for sentence in _closing_sentences(client, db, note, diagnosis, concern, comprehensive=bool(care)):
            if not room():
                break
            try:
                reply = say(sentence)
                said.append(sentence)
                if QUESTION_CUE.search(reply or "") and not NO_QUESTION.search(_nfc(reply)):
                    pending_question = reply
            except NovaError as exc:
                st["stopped"] = getattr(exc, "code", "") in STOP_CODES
                break
        if pending_question and room():
            try:
                answer = _answer_question(client, note, diagnosis, pending_question)
                say(answer)
                said.append(answer)
            except NovaError:
                pass
        elif room(2):
            try:
                reply = say(QUESTIONS_Q)
                if QUESTION_CUE.search(reply or "") and not NO_QUESTION.search(_nfc(reply)):
                    answer = _answer_question(client, note, diagnosis, reply)
                    if room():
                        say(answer)
                        said.append(answer)
            except NovaError:
                pass
'''


def patched_source(source: str) -> str:
    if source.count(OLD) != 1:
        raise ValueError("unexpected upstream E2 closing contract")
    return source.replace(OLD, NEW)


def install():
    from examples import hybrid_care, hybrid_comm
    source = Path(hybrid_comm.__file__).read_text(encoding="utf-8")
    module = types.ModuleType("examples.hybrid_comm_pending")
    module.__file__ = hybrid_comm.__file__
    exec(compile(patched_source(source), module.__file__, "exec"), module.__dict__)
    original = hybrid_care.base_consult
    hybrid_care.base_consult = module.consult
    return original


def restore(original):
    from examples import hybrid_care
    hybrid_care.base_consult = original
