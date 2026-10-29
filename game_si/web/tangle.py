"""Absolute tangle measures of one analysis, compared with the first analysis (= 100)."""
from __future__ import annotations

import networkx as nx

COMPLEX_CC = 20
BASE_CC = 10
COMPONENTS = [
    ('cycle_units', '순환 고리에 묶인 단위'),
    ('links', '단위 사이 연결'),
    # How far the complex functions go past CC 20, not how many there are: a count treats CC 375 and CC 21
    # alike, so splitting one huge function into several CC 21–60 pieces raised it (OpenTyrian 2026-10-26: 56 → 65
    # while the total past 20 fell 3,967 → 3,403). Changed 2026-10-29 after the rehearsal.
    ('complex_excess', f'매우 복잡한 부분 Σ(CC−{COMPLEX_CC})'),
    ('excess_complexity', f'초과 복잡도 Σ(CC−{BASE_CC})'),
    ('global_access', '전역 변수 접근'),
]


def graph(metrics: dict) -> nx.DiGraph:
    g = nx.DiGraph()
    names = {c['fqn'] for c in metrics.get('classes', [])}
    g.add_nodes_from(names)
    for c in metrics.get('classes', []):
        for target in c.get('out_neighbors', []):
            if target in names and target != c['fqn']:
                g.add_edge(c['fqn'], target)
    return g


def measure(metrics: dict, scoring: dict | None = None) -> dict:
    g = graph(metrics)
    ccs = [int(m.get('cc') or 0) for m in metrics.get('methods', [])]
    values = {
        'cycle_units': sum(len(s) for s in nx.strongly_connected_components(g) if len(s) > 1),
        'links': g.number_of_edges(),
        'complex_excess': sum(max(0, cc - COMPLEX_CC) for cc in ccs),
        'excess_complexity': sum(max(0, cc - BASE_CC) for cc in ccs),
        'global_access': int(sum(c.get('global_state') or 0 for c in metrics.get('classes', []))),
    }
    return {'values': values, 'units': sorted(g.nodes)}


def compare(baseline: dict, current: dict) -> dict:
    rows, ratios = [], []
    for key, label in COMPONENTS:
        before, after = baseline['values'][key], current['values'][key]
        included = before > 0
        if included:
            ratios.append(after / before)
        rows.append({'key': key, 'label': label, 'before': before, 'after': after, 'included': included})
    index = round(100 * sum(ratios) / len(ratios), 2) if ratios else 100.0
    return {'index': index, 'components': rows, 'same_units': baseline['units'] == current['units']}
