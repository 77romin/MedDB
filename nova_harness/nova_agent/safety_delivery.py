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


def patient_korean(text):
    """Patient-facing closing prose must contain Korean, not Japanese output."""
    return isinstance(text,str) and bool(re.search(r'[가-힣]',text)) and not re.search(r'[\u3040-\u30ff]',text)


def complete_sentences(value,limit=30):
    value=unicodedata.normalize('NFC',str(value or '')).strip()
    if not value or '?' in value or not patient_korean(value):return []
    # Preserve the old valid single-field behavior. Splitting is used only when
    # the WHOLE field is over the action limit; never clip a long sentence.
    if len(value)<=limit:return [value]
    chunks=[part.strip() for part in re.split(r'(?<=[.!。])\s+|\n+',value) if part.strip()]
    if len(chunks)<2 or any(len(part)>limit for part in chunks):return []
    if any(not re.search(r'(?:[.!。]|세요|해요|게요|어요|아요|니다|예요|이에요)$',part) for part in chunks):return []
    return chunks


def numbers(text):
    return set(re.findall(r'\d+(?:\.\d+)?',str(text)))


def source_spans(quote,source):
    """Accept one exact span, or ordered COMPLETE source sentences, never paraphrase."""
    if quote in source:return [(source.index(quote),source.index(quote)+len(quote))]
    chunks=[s.strip() for s in re.split(r'(?<=[.!。])\s+',quote.strip()) if s.strip()]
    if len(chunks)<2 or any(not s.endswith(('.', '!', '。')) for s in chunks):raise ValueError('source quote mismatch')
    spans=[];cursor=0
    for chunk in chunks:
        index=source.find(chunk,cursor)
        if index<0 or (index and source[index-1] not in ' \n.!。'):raise ValueError('source quote mismatch')
        # No quote may start inside a sentence after an ordinary space.
        previous=source[:index].rstrip()
        if previous and previous[-1] not in '.!。':raise ValueError('non-sentence source span')
        spans.append((index,index+len(chunk)));cursor=index+len(chunk)
    return spans


def split_condition_list(text,limit=30):
    """Repeat the SAME action for intact enumerated conditions; no medical rewrite."""
    text=unicodedata.normalize('NFC',text).strip()
    if not patient_korean(text):return []
    match=re.fullmatch(r'(.+?)( 땐 |일 때 |이면 | 시 | 생기면 )(.+)',text)
    if not match:return []
    items=[v.strip() for v in re.split(r'[·,]',match[1]) if v.strip()]
    if len(items)<2:return []
    suffix=match[2]+match[3];groups=[];current=[]
    for item in items:
        if len(item+suffix)>limit:return []
        if current and len('·'.join(current+[item])+suffix)>limit:
            groups.append('·'.join(current)+suffix);current=[]
        current.append(item)
    if current:groups.append('·'.join(current)+suffix)
    return groups


def validate_addendum(payload,note,allowed_fields=('disposition','education','follow_up','treatment'),audit=None):
    """Structural/provenance validation, NOT proof of clinical entailment."""
    if not isinstance(payload,dict) or payload.get('status') not in ('consistent','needs_clarification','uncertain'):
        raise ValueError('invalid audit status')
    missing=payload.get('missing',[])
    if not isinstance(missing,list) or len(missing)>2:raise ValueError('invalid addendum count')
    if payload['status']!='needs_clarification':
        if missing:raise ValueError('non-actionable audit contains additions')
        return []
    messages=[];rejected=0
    for item in missing:
        try:
            field=item.get('source_field');quote=item.get('source_quote');parts=item.get('messages')
            source=note.get('P',{}).get(field,'') if field in allowed_fields else ''
            if not isinstance(quote,str) or not quote.strip():raise ValueError('missing quote')
            source_spans(quote,source)
            if not isinstance(parts,list) or not 1<=len(parts)<=2:raise ValueError('invalid messages')
            group=[]
            for text in parts:
                if not isinstance(text,str) or not text.strip() or '?' in text:raise ValueError('invalid speech')
                if not numbers(text)<=numbers(quote):raise ValueError('new numeric advice')
                expanded=complete_sentences(text) or split_condition_list(text)
                if not expanded:raise ValueError('invalid speech length')
                group.extend(expanded)
            if len(messages)+len(group)>2:raise ValueError('complete group exceeds speech budget')
            messages.extend(group)
        except (ValueError,AttributeError,TypeError):
            rejected+=1
    if audit is not None:audit.update(rejected_groups=rejected,accepted_sentences=len(messages))
    if missing and not messages:raise ValueError('no valid complete source-backed addendum')
    return messages
