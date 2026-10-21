"""Lossless sentence recovery for an existing closing response.

No clinical text is invented, truncated, or translated here. Each returned
sentence is a complete substring of a fully decoded JSON string.
"""
import json
import re
import unicodedata

KEYS=('diagnosis','plan','follow_up','safety','concern')


def complete_fields(text):
    """Recover only fully terminated JSON strings, even after response truncation."""
    if not isinstance(text,str):return {}
    decoder=json.JSONDecoder();found={}
    for match in re.finditer(r'"(diagnosis|plan|follow_up|safety|concern)"\s*:\s*',text):
        try:value,_=decoder.raw_decode(text,match.end())
        except (ValueError,json.JSONDecodeError):continue
        if isinstance(value,str):found[match.group(1)]=value
    return found


def complete_sentences(value,limit=30):
    value=unicodedata.normalize('NFC',str(value or '')).strip()
    if not value or '?' in value:return []
    # Preserve the old valid single-field behavior. Splitting is used only when
    # the WHOLE field is over the action limit; never clip a long sentence.
    if len(value)<=limit:return [value]
    chunks=[part.strip() for part in re.split(r'(?<=[.!。])\s+|\n+',value) if part.strip()]
    if len(chunks)<2 or any(len(part)>limit for part in chunks):return []
    if any(not re.search(r'(?:[.!。]|세요|해요|게요|어요|아요|니다|예요|이에요)$',part) for part in chunks):return []
    return chunks


def numbers(text):
    return set(re.findall(r'\d+(?:\.\d+)?',str(text)))


def validate_addendum(payload,note,allowed_fields=('disposition','education','follow_up','treatment')):
    """Structural/provenance validation, NOT proof of clinical entailment."""
    if not isinstance(payload,dict) or payload.get('status') not in ('consistent','needs_clarification','uncertain'):
        raise ValueError('invalid audit status')
    missing=payload.get('missing',[])
    if not isinstance(missing,list) or len(missing)>2:raise ValueError('invalid addendum count')
    if payload['status']!='needs_clarification':
        if missing:raise ValueError('non-actionable audit contains additions')
        return []
    messages=[]
    for item in missing:
        field=item.get('source_field');quote=item.get('source_quote');parts=item.get('messages')
        source=note.get('P',{}).get(field,'') if field in allowed_fields else ''
        if not isinstance(quote,str) or not quote.strip() or quote not in source:raise ValueError('source quote mismatch')
        if not isinstance(parts,list) or not 1<=len(parts)<=2:raise ValueError('invalid messages')
        for text in parts:
            if not isinstance(text,str) or not text.strip() or len(unicodedata.normalize('NFC',text))>30 or '?' in text:
                raise ValueError('invalid speech length')
            if not numbers(text)<=numbers(quote):raise ValueError('new numeric advice')
            messages.append(unicodedata.normalize('NFC',text).strip())
    if len(messages)>2:raise ValueError('speech budget exceeded')
    return messages
