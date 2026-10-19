"""Preserve a complete <=30 character clause from an overlong E2 answer."""
import types
from pathlib import Path

OLD = '''    text = text.splitlines()[0].strip() if text else ""
    return text if _fits(text) and "?" not in text else default
'''
NEW = '''    text = text.splitlines()[0].strip() if text else ""
    if _fits(text) and "?" not in text:
        return text
    if text and "?" not in text:
        clauses = [_nfc(part) for part in re.split(r"[,，]", text)]
        candidates = []
        for part in clauses:
            candidates.append(part)
            if "한 뒤 " in part:
                candidates.append(_nfc(part.split("한 뒤 ", 1)[1]))
            if "와 " in part:
                candidates.append(_nfc(part.rsplit("와 ", 1)[1]))
        complete = [part for part in candidates if _fits(part) and re.search(r"[요다죠]\\.?$", part)]
        if complete:
            return max(complete, key=len)
    return default
'''


def patched_source(source: str) -> str:
    if source.count(OLD) != 1:
        raise ValueError("unexpected upstream E2 answer contract")
    return source.replace(OLD, NEW)


def install():
    from examples import hybrid_care, hybrid_comm
    source = Path(hybrid_comm.__file__).read_text(encoding="utf-8")
    module = types.ModuleType("examples.hybrid_comm_answer_compact")
    module.__file__ = hybrid_comm.__file__
    exec(compile(patched_source(source), module.__file__, "exec"), module.__dict__)
    original = hybrid_care.base_consult
    hybrid_care.base_consult = module.consult
    return original


def restore(original):
    from examples import hybrid_care
    hybrid_care.base_consult = original
