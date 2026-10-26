"""Diagnosis payload for the redesigned web UI, computed from metrics.json and scoring.json."""
from __future__ import annotations

import bisect
import hashlib
import json
from pathlib import Path

import networkx as nx

from .tangle import graph

KEYS = ['cc', 'coupling', 'dependency_cycle', 'global_state', 'game_loop_centrality']
LEVERAGE_LIMIT = 80
VERSION = 4   # 2: node labels and analysis backend in the summary; 3: rank per measure; 4: every cycle counted, tie sizes


def _largest(g):
    return max((len(s) for s in nx.strongly_connected_components(g) if len(s) > 1), default=0)


def _pct(column, value):
    # bar width: share of other units below this value (min → 0, max → 100)
    return round(100 * bisect.bisect_left(column, value) / (len(column) - 1)) if len(column) > 1 else 0


def _top(column, value):
    # "상위 n%": share of units at or above this value
    return max(1, round(100 * (len(column) - bisect.bisect_left(column, value)) / len(column)))


def _rank(column, value):
    # "n위": 1 + units with a strictly larger value; equal values share the rank ("공동").
    return len(column) - bisect.bisect_right(column, value) + 1


def _label(language):
    return '파일' if (language or '').lower() in {'c', 'cpp', 'c++', 'clang'} else '클래스'


def _subject(label):
    return label + ('이' if label == '파일' else '가')


def _sentence(unit, label):
    parts = []
    for key in sorted(KEYS, key=lambda k: -unit['pct'][k]):
        if unit['pct'][key] < 60 or len(parts) == 2:
            continue
        raw = unit['raw'][key]
        if key == 'cc' and unit['functions']:
            f = unit['functions'][0]
            parts.append(f"가장 복잡한 함수 {f['name']}의 복잡도(CC)가 {f['cc']}입니다")
        elif key == 'coupling':
            parts.append(f"다른 {label} {len(unit['calls'])}곳을 부르고 {len(unit['called_by'])}곳에서 불립니다")
        elif key == 'dependency_cycle' and unit['in_cycle']:
            parts.append(f"{unit['cycle_size']}개 {_subject(label)} 서로 부르는 순환 고리 안에 있습니다")
        elif key == 'global_state' and raw:
            parts.append(f"전역 변수를 {int(raw)}번 읽고 바꿉니다")
        elif key == 'game_loop_centrality' and raw:
            parts.append('매 프레임 실행 흐름과 가깝습니다')
    return '. '.join(parts) + '.' if parts else f'다른 {label}보다 두드러진 엉킴 요인이 적습니다.'


def build(metrics: dict, scoring: dict) -> dict:
    g = graph(metrics)
    status = scoring.get('analysis_status', {})
    label = _label(status.get('language'))
    scores = sorted(scoring.get('class_scores', []), key=lambda c: -c['si'])
    columns = {k: sorted(c['raw'][k] for c in scores) for k in KEYS}
    by_class = {c['fqn']: c for c in metrics.get('classes', [])}
    methods = {}
    for m in metrics.get('methods', []):
        methods.setdefault(m.get('class_fqn'), []).append(m)
    components = [s for s in nx.strongly_connected_components(g) if len(s) > 1]
    cycle = max(components, key=len, default=set())
    base = len(cycle)
    hubs = sorted(cycle, key=lambda n: -(g.in_degree(n) + g.out_degree(n)))[:LEVERAGE_LIMIT]
    leverage = {}
    for n in hubs:
        h = g.copy()
        h.remove_node(n)
        leverage[n] = max(0, base - 1 - _largest(h))
    in_any = set().union(*components) if components else set()
    cycle_of = {n: len(s) for s in components for n in s}   # each unit's own cycle (a project can have several)
    si = {c['fqn']: c['si'] for c in scores}
    units = []
    for c in scores:
        k = by_class.get(c['fqn'], {})
        fs = sorted(methods.get(c['fqn'], []), key=lambda m: (-(m.get('cc') or 0), m.get('start_line') or 0))
        unit = {'fqn': c['fqn'], 'name': c['name'], 'file': c.get('file_path', ''), 'grade': c['grade'],
                'si': c['si'], 'loc': c.get('loc', 0), 'raw': c['raw'],
                'pct': {key: _pct(columns[key], c['raw'][key]) for key in KEYS},
                'top': {key: _top(columns[key], c['raw'][key]) for key in KEYS},
                'rank': {key: _rank(columns[key], c['raw'][key]) for key in KEYS},
                'tied': {key: bisect.bisect_right(columns[key], c['raw'][key]) - bisect.bisect_left(columns[key], c['raw'][key]) > 1
                         for key in KEYS},
                'tie_count': {key: bisect.bisect_right(columns[key], c['raw'][key]) - bisect.bisect_left(columns[key], c['raw'][key])
                              for key in KEYS},
                'calls': sorted((t for t in k.get('out_neighbors', []) if t in si), key=lambda t: -si[t]),
                'called_by': sorted((t for t in k.get('in_neighbors', []) if t in si), key=lambda t: -si[t]),
                'in_cycle': c['fqn'] in in_any, 'cycle_size': cycle_of.get(c['fqn'], 0), 'leverage': leverage.get(c['fqn'], 0),
                'functions': [{'name': m['name'], 'cc': m.get('cc') or 0, 'loc': m.get('loc') or 0,
                               'line': m.get('start_line') or 0} for m in fs[:5]],
                'function_count': len(fs)}
        unit['sentence'] = _sentence(unit, label)
        units.append(unit)
    worst = max(metrics.get('methods', []), key=lambda m: m.get('cc') or 0, default=None)
    e_count = scoring.get('grade_distribution', {}).get('E', 0)
    summary = {'unit_label': label, 'units': len(units), 'functions': len(metrics.get('methods', [])),
               'grades': scoring.get('grade_distribution', {}), 'e_count': e_count,
               'cycle_size': base, 'cycle_units': len(in_any), 'cycles': len(components), 'links': g.number_of_edges(),
               'worst_function': {'unit': worst.get('class_fqn'), 'name': worst.get('name'), 'cc': worst.get('cc') or 0,
                                  'loc': worst.get('loc') or 0} if worst else None,
               'state': status.get('state'), 'language': status.get('language'),
               'backend': status.get('backend') or ('roslyn' if status.get('language') == 'csharp' else 'tree-sitter'),
               'syntax_files': status.get('syntax_files', 0),
               'compiler_error_files': status.get('compiler_error_files', 0)}
    # The same count the result page compares: every unit in any cycle, not only the largest cycle.
    tail = ('순환 고리는 없습니다.' if not components
            else f'{base}개 {_subject(label)} 하나의 순환 고리로 묶여 있습니다.' if len(components) == 1
            else f'{len(in_any)}개 {_subject(label)} 순환 고리 {len(components)}개로 묶여 있습니다.')
    headline = f'{len(units)}개 {label} 중 {e_count}개가 심하게 엉켜 있고, {tail}'
    # label: the short name shown on the map ('game_menu.c' rather than 'clang.file.game_menu.c').
    nodes = [{'id': u['fqn'], 'label': u['name'] or u['fqn'], 'si': u['si'], 'grade': u['grade'], 'loc': u['loc'], 'in_cycle': u['in_cycle'],
              'leverage': u['leverage'], 'fin': len(u['called_by']), 'fout': len(u['calls']),
              'top': u['functions'][0] if u['functions'] else None} for u in units]
    return {'version': VERSION, 'headline': headline, 'summary': summary, 'units': units,
            'graph': {'nodes': nodes, 'edges': [list(e) for e in g.edges]}}


def load(result: Path) -> dict:
    scoring_raw = (result / 'scoring.json').read_bytes()
    metrics_raw = (result / 'metrics.json').read_bytes()
    fingerprint = hashlib.sha256(scoring_raw + b'\0' + metrics_raw).hexdigest()
    cache = result / 'diagnosis.json'
    try:
        cached = json.loads(cache.read_text('utf8'))
        if cached.get('fingerprint') == fingerprint and cached.get('version') == VERSION:
            return cached
    except (OSError, ValueError):
        pass
    data = build(json.loads(metrics_raw), json.loads(scoring_raw))
    data['fingerprint'] = fingerprint
    try:
        cache.write_text(json.dumps(data, ensure_ascii=False), encoding='utf8')
    except OSError:
        pass
    return data
