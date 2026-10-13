"""Same agent can switch only the knowledge provider using the runner's mode."""
import importlib.util
import os
from pathlib import Path


def provider():
    mode=os.environ.get('NOVA_KB_MODE','improved_kb')
    if mode=='no_kb':return lambda request:None
    if mode not in {'previous_kb','improved_kb'}:raise ValueError('Unknown comparison mode')
    root=Path(__file__).resolve().parents[1]
    spec=importlib.util.spec_from_file_location('offline_comparison_tools',root/'tools/compare_knowledge_offline.py')
    tool=importlib.util.module_from_spec(spec);spec.loader.exec_module(tool)
    path=os.environ.get('NOVA_KB_SNAPSHOT_DIR')
    if not path:raise ValueError('A frozen knowledge snapshot directory is required')
    kb=tool.load_snapshot(path)
    return lambda request:tool.support(kb,request,mode)
