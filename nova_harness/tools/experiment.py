"""Run public development samples; never performs an official leaderboard submission."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nova_agent.analysis import write_report
from nova_agent.config import Config
from nova_agent import __version__
from nova_agent.protocol import Gateway, LoggedClient
from nova_agent.runtime import prepare, consult
from nova_agent.telemetry import Trace
from nova_sdk import NovaError


def load_local_env():
    path = ROOT/'.env'
    if not path.exists():
        return
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[7:]
        k, sep, v = line.partition('=')
        if sep and k.strip() in {'NOVA_DEV_KEY', 'NOVA_API_BASE'}:
            os.environ.setdefault(k.strip(), v.strip().strip('\"\''))


def fingerprint():
    paths = [ROOT/'run.py', ROOT/'nova_sdk.py', *sorted((ROOT/'nova_agent').glob('*.py')),
             *sorted((ROOT/'nova_agent').glob('*.json')), ROOT/'vendor/starter/run.py']
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.exists()}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('check')
    sub.add_parser('list')
    r = sub.add_parser('run')
    r.add_argument('--case', required=True, help='published sample UUID from list; no answer files loaded')
    r.add_argument('--agent', choices=['baseline', 'harness', 'meddb_e2', 'meddb_e2_plus', 'meddb_e2_calibrated', 'meddb_e2_direct_answer'], default='harness')
    r.add_argument('--max-turns', type=int, default=30)
    r.add_argument('--label', default='')
    r.add_argument('--no-meddb', action='store_true', help='ablation: disable imported clinical graph advice')
    r.add_argument('--no-structured-closing', action='store_true', help='ablation: let the planner manage closing')
    r.add_argument('--no-coverage', action='store_true', help='ablation: disable graph-derived collection gate')
    r.add_argument('--no-decision-review', action='store_true', help='ablation: disable scoped goals and bounded DONE review')
    r.add_argument('--planner-effort', choices=['low','medium','high'], default=Config().planner_reasoning_effort)
    r.add_argument('--full-context', action='store_true', help='ablation: retain all unconfirmed ontology ids')
    r.add_argument('--guidelines', action='store_true', help='optional read-only official guideline retrieval')
    closure = r.add_mutually_exclusive_group()
    closure.add_argument('--closure-audit', action='store_true', help='experimental: enable one bounded pre-exit review')
    closure.add_argument('--no-closure-audit', action='store_true', help='explicit control: disable pre-exit review (default)')
    a = sub.add_parser('analyze'); a.add_argument('trace')
    args = p.parse_args()
    if args.command == 'analyze':
        print(json.dumps(write_report(args.trace), ensure_ascii=False, indent=2)); return 0
    load_local_env()
    key = os.environ.get('NOVA_DEV_KEY', '').strip()
    base = os.environ.get('NOVA_API_BASE', 'https://nova.snubhai.org').rstrip('/')
    if base != 'https://nova.snubhai.org':
        p.error('development credentials are sent only to the official NOVA origin')
    if args.command == 'check':
        print(json.dumps({'api_base': base, 'development_key_configured': bool(key),
                          'sdk': '1.0.1', 'doctor': Config().model}, ensure_ascii=False)); return 0
    if not key:
        p.error('NOVA_DEV_KEY is missing; set it in local .env (never paste into chat)')
    if args.command == 'list':
        client = LoggedClient(api_base=base, token=key, sample=True)
        cases = client._request('GET', '/v1/sample/cases')
        print(json.dumps(cases, ensure_ascii=False, indent=2)); return 0
    if not 1 <= args.max_turns <= 45:
        p.error('--max-turns must be 1–45')
    stamp = datetime.now(timezone(timedelta(hours=9))).strftime('%Y%m%d_%H%M%S_%f')
    directory = ROOT/'results'/f'{stamp}_{args.agent}'
    directory.mkdir(parents=True, mode=0o700)
    trace = Trace(directory/'trace.jsonl', secrets=[key])
    manifest = {'agent': args.agent, 'case_id': args.case, 'label': args.label,
                'agent_version':__version__,
                'max_turns': args.max_turns, 'fingerprint': fingerprint(), 'model': Config().model,
                'closure_audit': args.agent == 'harness' and args.closure_audit,
                'meddb': args.agent == 'harness' and not args.no_meddb,
                'structured_closing': args.agent == 'harness' and not args.no_structured_closing,
                'coverage':args.agent == 'harness' and not args.no_coverage,
                'decision_review':args.agent == 'harness' and not args.no_decision_review,
                'telemetry_features': ([name for name, enabled in (
                    ('decision_goals', not args.no_decision_review),
                    ('patient_question_tracking', not args.no_structured_closing)) if enabled]
                    if args.agent == 'harness' else []),
                'compact_context':args.agent == 'harness' and not args.full_context,
                'guidelines':args.agent == 'harness' and args.guidelines,
                'closing_turns':Config().closing_turns,
                'planner_reasoning_effort':args.planner_effort if args.agent == 'harness' else None,
                'final_reasoning_effort':Config().reasoning_effort if args.agent == 'harness' else None,
                'python': sys.version, 'started_kst': stamp,
                'evaluation_mode': 'development_sample_no_official_score'}
    if args.agent in {'meddb_e2','meddb_e2_plus','meddb_e2_calibrated','meddb_e2_direct_answer'}:
        repo = ROOT/'vendor/meddb'
        manifest['upstream_commit'] = subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
        manifest['turn_policy'] = 'Unmodified upstream E2: up to 36 collection turns plus closing; server limit 50. --max-turns does not override upstream policy.'
        manifest['max_turns'] = 50
        for path in [*sorted((repo/'meddb').rglob('*.py')), *sorted((repo/'meddb/data').glob('*')),
                     *sorted((repo/'examples').glob('*.py'))]:
            if path.is_file(): manifest['fingerprint'][str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    (directory/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    with zipfile.ZipFile(directory/'source_snapshot.zip', 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for name in manifest['fingerprint']:
            z.write(ROOT/name, name)
    trace.emit('experiment_start', manifest=manifest)
    client = LoggedClient(api_base=base, token=key, sample=True, trace=trace)
    print('Experiment directory:', directory, flush=True)
    code = 0
    try:
        Gateway(client, trace=trace).invoke('create_sample', args.case)
        if args.agent == 'baseline':
            path = ROOT/'vendor/starter/run.py'
            spec = importlib.util.spec_from_file_location('nova_official_baseline', path)
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            module.MAX_TURNS = args.max_turns
            outcome = module.consult(client, module.prepare())
        elif args.agent in {'meddb_e2','meddb_e2_plus','meddb_e2_calibrated','meddb_e2_direct_answer'}:
            sys.path.insert(0,str(ROOT/'vendor/meddb'))
            from examples.hybrid_care import prepare as meddb_prepare, consult as meddb_consult
            original = None
            if args.agent == 'meddb_e2_plus':
                from nova_agent.meddb_overlay import install
                original=install()
            elif args.agent == 'meddb_e2_calibrated':
                from nova_agent.e2_calibrated import install
                original=install()
            elif args.agent == 'meddb_e2_direct_answer':
                from nova_agent.e2_direct_answer import install
                original=install()
            try:
                outcome = meddb_consult(client, meddb_prepare(), knowledge_mode='clinical', reference_profile='reviewed')
            finally:
                if original:
                    if args.agent == 'meddb_e2_plus':
                        from nova_agent.meddb_overlay import restore
                    elif args.agent == 'meddb_e2_calibrated':
                        from nova_agent.e2_calibrated import restore
                    else:
                        from nova_agent.e2_direct_answer import restore
                    restore(original)
        else:
            outcome = consult(client, prepare(), Config(max_turns=args.max_turns, closure_audit=args.closure_audit,
                                meddb=not args.no_meddb, coverage=not args.no_coverage, compact_context=not args.full_context, guidelines=args.guidelines,
                                decision_review=not args.no_decision_review,
                                planner_reasoning_effort=args.planner_effort, structured_closing=not args.no_structured_closing), trace)
        trace.emit('experiment_complete', result=outcome)
    except Exception as exc:
        code = 1
        # No traceback/environment/header dumps; retain a scrubbed error in local logs.
        trace.emit('experiment_failed', exception=type(exc).__name__, code=getattr(exc, 'code', None), message=str(exc))
        print('Experiment failed; inspect the redacted local trace.', flush=True)
    result = write_report(directory/'trace.jsonl')
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return code


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except NovaError as exc:
        print('NOVA API error:', exc.code, file=sys.stderr)
        raise SystemExit(1)
