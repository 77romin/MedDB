import json
import re
import unicodedata

from nova_sdk import RECORD_FIELDS


def parse_object(text):
    if not isinstance(text, str):
        raise ValueError('model content must be a string')
    text = text.strip()
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
    result = json.loads(text)
    if not isinstance(result, dict):
        raise ValueError('model output must be one JSON object')
    return result


def action_key(action, content):
    return action, re.sub(r'[\s?!？！.。]+', '', unicodedata.normalize('NFC', content)).casefold()


def validate_action(value, seen=()):
    if not isinstance(value, dict) or not isinstance(value.get('type'), str):
        raise ValueError('next_action.type is required')
    action = value['type'].upper()
    if action == 'DONE':
        return action, ''
    if action not in {'SAY', 'EXAM'}:
        raise ValueError('preliminary round permits only SAY, EXAM, DONE')
    if not isinstance(value.get('content'), str):
        raise ValueError('action content must be a string')
    content = unicodedata.normalize('NFC', value['content']).strip()
    if not 0 < len(content) <= 30:
        raise ValueError('content must be 1–30 NFC code points; regenerate, do not truncate')
    if action_key(action, content) in seen:
        raise ValueError('exact duplicate action; choose new information or explanation')
    # This catches explicit compound questions. Semantic single-item validation remains a model task.
    if action == 'SAY' and content.count('?') + content.count('？') > 1:
        raise ValueError('only one question per SAY')
    return action, content


def validate_record(note, diagnosis):
    if not isinstance(note, dict) or set(note) != set(RECORD_FIELDS):
        raise ValueError('invalid SOAP sections')
    for section, fields in RECORD_FIELDS.items():
        if not isinstance(note[section], dict) or set(note[section]) != set(fields):
            raise ValueError('invalid SOAP fields: '+section)
        if any(not isinstance(v, str) for v in note[section].values()):
            raise ValueError('all SOAP fields must be strings')
    if not any(v.strip() for sec in note.values() for v in sec.values()):
        raise ValueError('empty record')
    if len(json.dumps(note, ensure_ascii=False).encode('utf-8')) > 100_000:
        raise ValueError('record exceeds UTF-8 byte budget')
    if not isinstance(diagnosis, str) or not diagnosis.strip() or '\n' in diagnosis or len(diagnosis.encode('utf-8')) > 500:
        raise ValueError('diagnosis must be one nonempty line, at most 500 bytes')
