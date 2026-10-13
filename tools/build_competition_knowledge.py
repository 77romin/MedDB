"""Lossless PPTX archive and offline text-vector retrieval. Standard library only."""
import argparse
import collections
import hashlib
import html
import json
import math
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1] / 'docs' / 'nova_competition'
NS = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def paragraphs(root):
    return [''.join(t.text or '' for t in p.findall('.//a:t', NS))
            for p in root.findall('.//a:p', NS)]


def features(text):
    text = re.sub(r'\s+', ' ', text.lower())
    words = re.findall(r'\w+', text)
    return collections.Counter(words + [text[i:i+n] for n in (2, 3) for i in range(max(0, len(text)-n+1)) if text[i:i+n].strip()])


def vector(counts, idf):
    values = {k: (1 + math.log(v)) * idf[k] for k, v in counts.items() if k in idf}
    norm = math.sqrt(sum(v*v for v in values.values())) or 1
    return {k: v/norm for k, v in values.items()}


def build(files):
    ROOT.mkdir(parents=True, exist_ok=True)
    chunks, reports = [], []
    for index, source in enumerate(files, 1):
        source = Path(source)
        folder = ROOT / f'deck_{index:02d}'
        folder.mkdir(exist_ok=True)
        copied = folder / source.name
        shutil.copy2(source, copied)
        archive = folder / 'package'
        archive.mkdir(exist_ok=True)
        entries = []
        text_parts = {}
        with zipfile.ZipFile(copied) as z:
            for info in z.infolist():
                target = (archive / info.filename).resolve()
                if not target.is_relative_to(archive.resolve()):
                    raise ValueError('Unsafe archive path')
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                data = z.read(info)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                entries.append({'part': info.filename, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
                if info.filename.endswith('.xml'):
                    node = ET.fromstring(data)
                    text_parts[info.filename] = {'paragraphs': paragraphs(node), 'all_text_nodes': list(node.itertext())}
        write_json(folder / 'all_xml_text.json', text_parts)
        presentation_rels = {r.get('Id'): r.get('Target') for r in ET.parse(archive / 'ppt/_rels/presentation.xml.rels').getroot()}
        presentation = ET.parse(archive / 'ppt/presentation.xml').getroot()
        slide_names = ['ppt/' + presentation_rels[s.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')].lstrip('/') for s in presentation.findall('.//{http://schemas.openxmlformats.org/presentationml/2006/main}sldId')]
        lines = [f'# {source.name}', '', '원문 텍스트를 수정하거나 요약하지 않은 추출 자료입니다. 이미지·도식·배치는 원본 PPT와 package를 함께 확인하세요.', '']
        page = [f'<meta charset="utf-8"><title>{html.escape(source.name)}</title><style>body{{max-width:1100px;margin:40px auto;font:16px/1.7 sans-serif}}pre{{white-space:pre-wrap}}img{{max-width:100%;max-height:600px}}section{{border-top:1px solid #aaa;padding:24px 0}}</style>', f'<h1>{html.escape(source.name)}</h1><p><a href="{html.escape(source.name)}">원본 PPT 열기</a></p>']
        for num, name in enumerate(slide_names, 1):
            # Preserve the presentation order and resolve the slide's actual notes/media relationships.
            rel_path = archive / 'ppt/slides/_rels' / (Path(name).name + '.rels')
            related = []
            if rel_path.exists():
                for rel in ET.parse(rel_path).getroot():
                    if rel.get('TargetMode') == 'External':
                        related.append({'type': rel.get('Type'), 'external': rel.get('Target')})
                    else:
                        target = (archive / 'ppt/slides' / rel.get('Target')).resolve()
                        related.append({'type': rel.get('Type'), 'part': target.relative_to(archive.resolve()).as_posix()})
            notes = [r['part'] for r in related if r.get('type', '').endswith('/notesSlide') and 'part' in r]
            body = '\n'.join(text_parts[name]['paragraphs'])
            note_text = '\n'.join('\n'.join(text_parts[n]['paragraphs']) for n in notes if n in text_parts)
            lines += [f'## 슬라이드 {num}', '', body, '', '### 발표자 노트', '', note_text or '(텍스트 없음)', '', '### 관련 파일', '', json.dumps(related, ensure_ascii=False, indent=2), '']
            chunk = {'id': f'd{index:02d}-s{num:03d}', 'source': source.name, 'slide': num, 'part': name, 'text': body + '\n발표자 노트\n' + note_text, 'related': related, 'original': str(copied.relative_to(ROOT)), 'reader': f'deck_{index:02d}/reader.html#slide-{num}'}
            chunks.append(chunk)
            page += [f'<section id="slide-{num}"><h2>슬라이드 {num}</h2><pre>{html.escape(body)}</pre><h3>발표자 노트</h3><pre>{html.escape(note_text)}</pre>']
            for rel in related:
                part = rel.get('part', '')
                if part.startswith('ppt/media/'):
                    url = 'package/' + part
                    page.append(f'<p><a href="{html.escape(url)}">{html.escape(part)}</a></p>')
                    if Path(part).suffix.lower() in ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'):
                        page.append(f'<img loading="lazy" src="{html.escape(url)}" alt="슬라이드 {num} 원본 미디어">')
            page.append('</section>')
        # Index XML outside slides/notes too, including charts, diagrams, layouts and comments.
        for name, values in text_parts.items():
            if name in slide_names or re.fullmatch(r'ppt/notesSlides/notesSlide\d+\.xml', name):
                continue
            text = '\n'.join(values['all_text_nodes']).strip()
            if text:
                chunks.append({'id': f'd{index:02d}-part-{name}', 'source': source.name, 'slide': None, 'part': name, 'text': text, 'original': str(copied.relative_to(ROOT))})
        (folder / 'slides.md').write_text('\n'.join(lines), encoding='utf-8')
        (folder / 'reader.html').write_text('\n'.join(page), encoding='utf-8')
        verified = all(hashlib.sha256((archive / e['part']).read_bytes()).hexdigest() == e['sha256'] for e in entries)
        reports.append({'source': str(source), 'copy': str(copied.relative_to(ROOT)), 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'copy_sha256': hashlib.sha256(copied.read_bytes()).hexdigest(), 'slides': len(slide_names), 'media': sum(e['part'].startswith('ppt/media/') for e in entries), 'all_package_parts_verified': verified, 'entries': entries})
    with (ROOT / 'chunks.jsonl').open('w', encoding='utf-8') as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + '\n')
    counts = [features(c['text']) for c in chunks]
    df = collections.Counter(k for count in counts for k in count)
    idf = {k: math.log((1+len(chunks))/(1+n))+1 for k,n in df.items()}
    write_json(ROOT / 'embeddings.json', {'method': 'L2-normalized word and character 2/3-gram TF-IDF; lexical, not neural semantic embeddings', 'idf': idf, 'vectors': [vector(c, idf) for c in counts]})
    write_json(ROOT / 'manifest.json', reports)
    print(json.dumps({'decks': len(reports), 'slides': sum(r['slides'] for r in reports), 'chunks': len(chunks), 'verified': all(r['all_package_parts_verified'] and r['source_sha256']==r['copy_sha256'] for r in reports)}, ensure_ascii=False))


def search(query, limit):
    chunks = [json.loads(line) for line in (ROOT / 'chunks.jsonl').read_text(encoding='utf-8').splitlines()]
    embeddings = json.loads((ROOT / 'embeddings.json').read_text(encoding='utf-8'))
    q = vector(features(query), embeddings['idf'])
    scores = [(sum(v * row.get(k, 0) for k,v in q.items()), i) for i,row in enumerate(embeddings['vectors'])]
    for score, i in sorted(scores, reverse=True)[:limit]:
        c = chunks[i]
        print(json.dumps({'score': round(score, 4), **c}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--build', nargs='+')
    parser.add_argument('--query')
    parser.add_argument('--limit', type=int, default=5)
    args = parser.parse_args()
    if args.build:
        build(args.build)
    elif args.query:
        search(args.query, args.limit)
    else:
        parser.error('Use --build FILE... or --query TEXT')
