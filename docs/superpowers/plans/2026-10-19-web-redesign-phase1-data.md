# 웹 재설계 1단계: 엉킴 총량·진단 데이터 계층 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 새 화면이 쓸 진단 데이터(단위·그래프·요약·레버리지·한 줄 설명)와 엉킴 총량(처음 상태 = 100)을 서버에서 계산해 API로 제공한다.

**Architecture:** 순수 함수 모듈 `game_si/web/tangle.py`(절대 지표·비교)와 `game_si/web/diagnosis.py`(진단 데이터)를 만들고, `app.py`에 읽기 전용 GET API 두 개를 추가한다. 입력은 기존 분석 산출물 `metrics.json`·`scoring.json`이며 분석기·점수 산식은 바꾸지 않는다. 진단 결과는 결과 폴더에 `diagnosis.json`으로 캐시한다.

**Tech Stack:** Python 3.10, networkx 3, FastAPI, pytest (TestClient)

Spec: `docs/superpowers/specs/2026-10-19-web-redesign-design.md` §3.2, §3.3, §4.2, §5.1

---

## 파일 구조

- Create `game_si/web/tangle.py` — 의존 그래프 생성, 다섯 절대 항목 측정, 기준 대비 엉킴 총량
- Create `game_si/web/diagnosis.py` — 백분위·이웃·순환·레버리지·상위 함수·한 줄 설명·요약·제목, 캐시
- Modify `game_si/web/app.py` — `GET /api/jobs/{id}/diagnosis`, `GET /api/jobs/{id}/tangle`
- Create `tests/test_tangle.py`, `tests/test_diagnosis.py`

공통 테스트 자료(두 테스트 파일에서 같은 모양을 사용):

```python
def sample(extra_cc=0, cut=False):
    # a→b→c→a 순환(3), d는 a를 부름. b는 전역 상태 5.
    out = {'a': ['b'], 'b': ['c'], 'c': [] if cut else ['a'], 'd': ['a']}
    classes = [{'fqn': n, 'name': n, 'file_path': f'{n}.c', 'out_neighbors': out[n],
                'in_neighbors': [k for k, v in out.items() if n in v],
                'global_state': 5 if n == 'b' else 0} for n in 'abcd']
    methods = [{'fqn': 'a.big', 'class_fqn': 'a', 'name': 'big', 'cc': 30 + extra_cc, 'loc': 90, 'start_line': 3},
               {'fqn': 'a.small', 'class_fqn': 'a', 'name': 'small', 'cc': 4, 'loc': 8, 'start_line': 99},
               {'fqn': 'b.mid', 'class_fqn': 'b', 'name': 'mid', 'cc': 12, 'loc': 30, 'start_line': 1}]
    raw = lambda cc, cp, cy, gs: {'cc': cc, 'coupling': cp, 'dependency_cycle': cy, 'global_state': gs, 'game_loop_centrality': 0.0}
    scores = [dict(fqn='a', name='a', file_path='a.c', loc=120, si=100.0, grade='E', raw=raw(30, 3, 2, 0)),
              dict(fqn='b', name='b', file_path='b.c', loc=40, si=75.0, grade='D', raw=raw(12, 2, 2, 5)),
              dict(fqn='c', name='c', file_path='c.c', loc=20, si=50.0, grade='C', raw=raw(1, 2, 2, 0)),
              dict(fqn='d', name='d', file_path='d.c', loc=10, si=25.0, grade='B', raw=raw(1, 1, 0, 0))]
    metrics = {'classes': classes, 'methods': methods, 'cycles': []}
    scoring = {'class_scores': scores, 'total_classes': 4, 'total_methods': 3,
               'grade_distribution': {'A': 0, 'B': 1, 'C': 1, 'D': 1, 'E': 1},
               'analysis_status': {'state': 'complete', 'language': 'c', 'syntax_files': 0}}
    return metrics, scoring
```

### Task 1: 엉킴 총량 (`tangle.py`)

**Files:** Create `game_si/web/tangle.py`, Test `tests/test_tangle.py`

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_tangle.py`에 위 `sample`과 다음 테스트를 둔다.

```python
from game_si.web import tangle

def test_measure_counts_absolute_components():
    m, s = sample()
    v = tangle.measure(m, s)['values']
    assert v == {'cycle_units': 3, 'links': 4, 'complex_functions': 1,
                 'excess_complexity': 22, 'global_access': 5}

def test_compare_is_100_for_same_result_and_drops_when_untangled():
    base = tangle.measure(*sample())
    assert tangle.compare(base, base)['index'] == 100.0
    after = tangle.measure(*sample(extra_cc=-15, cut=True))
    result = tangle.compare(base, after)
    rows = {r['key']: r for r in result['components']}
    assert rows['cycle_units']['after'] == 0 and rows['links']['after'] == 3
    assert rows['complex_functions']['after'] == 0
    assert result['index'] < 50 and result['same_units'] is True

def test_zero_baseline_components_are_excluded():
    m, s = sample()
    for c in m['classes']: c['global_state'] = 0
    base = tangle.measure(m, s)
    result = tangle.compare(base, base)
    assert 'global_access' not in {r['key'] for r in result['components'] if r['included']}
    assert result['index'] == 100.0

def test_unit_set_change_is_reported():
    base = tangle.measure(*sample())
    m, s = sample(); m['classes'].append({'fqn': 'e', 'name': 'e', 'file_path': 'e.c', 'out_neighbors': [], 'in_neighbors': [], 'global_state': 0})
    assert tangle.compare(base, tangle.measure(m, s))['same_units'] is False
```

- [ ] **Step 2:** `py -3.10 -m pytest tests/test_tangle.py -q` → FAIL (`ModuleNotFoundError: game_si.web.tangle`)
- [ ] **Step 3: 구현** — `game_si/web/tangle.py`

```python
"""Absolute tangle measures of one analysis, compared with the first analysis (= 100)."""
from __future__ import annotations

import networkx as nx

COMPLEX_CC = 20
BASE_CC = 10
COMPONENTS = [
    ('cycle_units', '순환 고리에 묶인 단위'),
    ('links', '단위 사이 연결'),
    ('complex_functions', f'매우 복잡한 함수 (CC>{COMPLEX_CC})'),
    ('excess_complexity', f'초과 복잡도 Σ(CC−{BASE_CC})'),
    ('global_access', '전역 상태 접근'),
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
        'complex_functions': sum(1 for cc in ccs if cc > COMPLEX_CC),
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
    index = round(100 * sum(ratios) / len(ratios), 1) if ratios else 100.0
    return {'index': index, 'components': rows, 'same_units': baseline['units'] == current['units']}
```

- [ ] **Step 4:** `py -3.10 -m pytest tests/test_tangle.py -q` → 4 passed

### Task 2: 진단 데이터 (`diagnosis.py`)

**Files:** Create `game_si/web/diagnosis.py`, Test `tests/test_diagnosis.py`

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_diagnosis.py` (같은 `sample` 포함)

```python
import json
from game_si.web import diagnosis

def test_units_have_percentiles_neighbors_cycle_and_functions():
    d = diagnosis.build(*sample())
    a = next(u for u in d['units'] if u['name'] == 'a')
    assert [u['name'] for u in d['units']] == ['a', 'b', 'c', 'd']          # G-SI 순
    assert a['calls'] == ['b'] and set(a['called_by']) == {'c', 'd'}
    assert a['in_cycle'] is True and a['functions'][0] == {'name': 'big', 'cc': 30, 'loc': 90, 'line': 3}
    assert a['function_count'] == 2 and a['pct']['cc'] == 100 and a['top']['cc'] == 25
    assert a['pct']['global_state'] == 0 and a['pct']['game_loop_centrality'] == 0
    assert next(u for u in d['units'] if u['name'] == 'd')['in_cycle'] is False

def test_leverage_is_cycle_reduction_when_unit_removed():
    d = diagnosis.build(*sample())
    lev = {u['name']: u['leverage'] for u in d['units']}
    assert lev == {'a': 2, 'b': 2, 'c': 2, 'd': 0}

def test_summary_headline_and_sentence_are_program_generated():
    d = diagnosis.build(*sample())
    s = d['summary']
    assert s['unit_label'] == '파일' and s['cycle_size'] == 3 and s['links'] == 4 and s['e_count'] == 1
    assert s['worst_function'] == {'unit': 'a', 'name': 'big', 'cc': 30, 'loc': 90}
    assert d['headline'] == '4개 파일 중 1개가 심하게 엉켜 있고, 3개 파일이 하나의 순환 고리로 묶여 있습니다.'
    a = next(u for u in d['units'] if u['name'] == 'a')
    assert a['sentence'].endswith('니다.') and 'big' in a['sentence']
    assert {n['id'] for n in d['graph']['nodes']} == set('abcd') and len(d['graph']['edges']) == 4

def test_class_language_uses_class_label_and_no_cycle_headline():
    m, s = sample(cut=True); s['analysis_status']['language'] = 'csharp'
    d = diagnosis.build(m, s)
    assert d['summary']['unit_label'] == '클래스'
    assert d['headline'] == '4개 클래스 중 1개가 심하게 엉켜 있고, 순환 고리는 없습니다.'

def test_load_caches_by_scoring_fingerprint(tmp_path):
    m, s = sample()
    (tmp_path / 'metrics.json').write_text(json.dumps(m)); (tmp_path / 'scoring.json').write_text(json.dumps(s))
    first = diagnosis.load(tmp_path)
    assert (tmp_path / 'diagnosis.json').is_file() and diagnosis.load(tmp_path) == first
    s['class_scores'][0]['si'] = 99.0; (tmp_path / 'scoring.json').write_text(json.dumps(s))
    assert diagnosis.load(tmp_path)['units'][0]['si'] == 99.0
```

- [ ] **Step 2:** `py -3.10 -m pytest tests/test_diagnosis.py -q` → FAIL (module missing)
- [ ] **Step 3: 구현** — `game_si/web/diagnosis.py` (아래 코드 블록 그대로)

```python
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
VERSION = 1


def _largest(g):
    return max((len(s) for s in nx.strongly_connected_components(g) if len(s) > 1), default=0)


def _pct(column, value):
    # bar width: share of other units below this value (min → 0, max → 100)
    return round(100 * bisect.bisect_left(column, value) / (len(column) - 1)) if len(column) > 1 else 0


def _top(column, value):
    # "상위 n%": share of units at or above this value
    return max(1, round(100 * (len(column) - bisect.bisect_left(column, value)) / len(column)))


def _label(language):
    return '파일' if (language or '').lower() in {'c', 'cpp', 'c++', 'clang'} else '클래스'


def _subject(label):
    return label + ('이' if label == '파일' else '가')


def _sentence(unit, cycle_size):
    parts = []
    for key in sorted(KEYS, key=lambda k: -unit['pct'][k]):
        if unit['pct'][key] < 60 or len(parts) == 2:
            continue
        raw = unit['raw'][key]
        if key == 'cc' and unit['functions']:
            f = unit['functions'][0]
            parts.append(f"가장 복잡한 함수 {f['name']}의 분기가 {f['cc']}개입니다")
        elif key == 'coupling':
            parts.append(f"다른 단위 {len(unit['calls'])}곳을 부르고 {len(unit['called_by'])}곳에서 불립니다")
        elif key == 'dependency_cycle' and unit['in_cycle']:
            parts.append(f"{cycle_size}개 단위가 얽힌 순환 고리 안에 있습니다")
        elif key == 'global_state' and raw:
            parts.append(f"공유 변수를 {int(raw)}번 읽고 바꿉니다")
        elif key == 'game_loop_centrality' and raw:
            parts.append('매 프레임 실행 흐름과 가깝습니다')
    return '. '.join(parts) + '.' if parts else '다른 단위보다 두드러진 엉킴 요인이 적습니다.'


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
        h = g.copy(); h.remove_node(n)
        leverage[n] = max(0, base - 1 - _largest(h))
    in_any = set().union(*components) if components else set()
    si = {c['fqn']: c['si'] for c in scores}
    units = []
    for c in scores:
        k = by_class.get(c['fqn'], {})
        fs = sorted(methods.get(c['fqn'], []), key=lambda m: (-(m.get('cc') or 0), m.get('start_line') or 0))
        unit = {'fqn': c['fqn'], 'name': c['name'], 'file': c.get('file_path', ''), 'grade': c['grade'],
                'si': c['si'], 'loc': c.get('loc', 0), 'raw': c['raw'],
                'pct': {key: _pct(columns[key], c['raw'][key]) for key in KEYS},
                'top': {key: _top(columns[key], c['raw'][key]) for key in KEYS},
                'calls': sorted((t for t in k.get('out_neighbors', []) if t in si), key=lambda t: -si[t]),
                'called_by': sorted((t for t in k.get('in_neighbors', []) if t in si), key=lambda t: -si[t]),
                'in_cycle': c['fqn'] in in_any, 'leverage': leverage.get(c['fqn'], 0),
                'functions': [{'name': m['name'], 'cc': m.get('cc') or 0, 'loc': m.get('loc') or 0, 'line': m.get('start_line') or 0} for m in fs[:5]],
                'function_count': len(fs)}
        unit['sentence'] = _sentence(unit, base)
        units.append(unit)
    worst = max(metrics.get('methods', []), key=lambda m: m.get('cc') or 0, default=None)
    e_count = scoring.get('grade_distribution', {}).get('E', 0)
    summary = {'unit_label': label, 'units': len(units), 'functions': len(metrics.get('methods', [])),
               'grades': scoring.get('grade_distribution', {}), 'e_count': e_count,
               'cycle_size': base, 'cycle_units': len(in_any), 'links': g.number_of_edges(),
               'worst_function': {'unit': worst['class_fqn'], 'name': worst['name'], 'cc': worst.get('cc') or 0,
                                  'loc': worst.get('loc') or 0} if worst else None,
               'state': status.get('state'), 'language': status.get('language'),
               'syntax_files': status.get('syntax_files', 0)}
    tail = f'{base}개 {_subject(label)} 하나의 순환 고리로 묶여 있습니다.' if base > 1 else '순환 고리는 없습니다.'
    headline = f'{len(units)}개 {label} 중 {e_count}개가 심하게 엉켜 있고, {tail}'
    nodes = [{'id': u['fqn'], 'si': u['si'], 'grade': u['grade'], 'loc': u['loc'], 'in_cycle': u['in_cycle'],
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
```

- [ ] **Step 4:** `py -3.10 -m pytest tests/test_diagnosis.py -q` → 5 passed

### Task 3: API

**Files:** Modify `game_si/web/app.py` (`/api/jobs/{ident}` 라우트 앞), Test `tests/test_diagnosis.py`

- [ ] **Step 1: 실패하는 API 테스트 추가** (`tests/test_diagnosis.py`)

```python
import pytest
pytest.importorskip('fastapi')
from fastapi.testclient import TestClient
from game_si.web.app import create_app

def test_diagnosis_and_tangle_api(tmp_path):
    app = create_app(tmp_path)
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        token = client.get('/api/session').json()['token']
        h = {'X-Game-SI-Token': token, 'Origin': 'http://127.0.0.1:8765'}
        job = client.post('/api/import/files', headers=h, data={'paths': json.dumps(['a.c']), 'name': 't'},
                          files=[('files', ('a.c', b'int f(){return 1;}', 'application/octet-stream'))]).json()
        manager = client.app.state.manager
        result = manager.directory(job['id']) / 'result'; result.mkdir()
        m, s = sample()
        (result / 'metrics.json').write_text(json.dumps(m)); (result / 'scoring.json').write_text(json.dumps(s))
        assert client.get(f"/api/jobs/{job['id']}/diagnosis").status_code == 409     # 아직 분석 전
        manager.update(job['id'], state='complete')
        d = client.get(f"/api/jobs/{job['id']}/diagnosis").json()
        assert d['summary']['cycle_size'] == 3 and 'fingerprint' in d
        t = client.get(f"/api/jobs/{job['id']}/tangle").json()
        assert t['rounds'][0] == {'round': 0, 'revision': None, 'index': 100.0, 'components': t['rounds'][0]['components'], 'same_units': True}
        assert client.get(f"/api/jobs/{job['id']}/diagnosis?revision={'0' * 32}").status_code == 404
        assert client.get(f"/api/jobs/{job['id']}/diagnosis?revision=../x").status_code == 400
```

- [ ] **Step 2:** `py -3.10 -m pytest tests/test_diagnosis.py::test_diagnosis_and_tangle_api -q` → FAIL (404)
- [ ] **Step 3: 구현** — `app.py`에 import와 라우트 추가

```python
from . import diagnosis, tangle as tangle_measure
...
    def result_folder(ident, revision=None):
        record = manager.get(ident)
        if record['state'] not in {'complete', 'partial'}:
            raise BusyError('분석이 끝난 뒤 진단을 볼 수 있습니다.')
        folder = manager.directory(ident) / 'result'
        if revision is not None:
            if not re.fullmatch('[a-f0-9]{32}', revision):
                raise ValueError('올바르지 않은 수정본 번호입니다.')
            folder = manager.directory(ident) / 'revisions' / revision / 'result'
        if not (folder / 'scoring.json').is_file() or not (folder / 'metrics.json').is_file():
            raise KeyError('result')
        return folder

    @app.get('/api/jobs/{ident}/diagnosis')
    def job_diagnosis(ident: str, revision: str | None = None):
        return diagnosis.load(result_folder(ident, revision))

    @app.get('/api/jobs/{ident}/tangle')
    def job_tangle(ident: str):
        def measured(folder):
            return tangle_measure.measure(json.loads((folder / 'metrics.json').read_text('utf8')))
        base = measured(result_folder(ident))
        rounds = [{'round': 0, 'revision': None, **tangle_measure.compare(base, base)}]
        return {'rounds': rounds}
```

(`json`은 이미 import되어 있는지 확인하고 없으면 추가. 라운드 목록은 5단계에서 `rounds.json`으로 확장한다.)

- [ ] **Step 4:** `py -3.10 -m pytest tests/test_diagnosis.py tests/test_tangle.py tests/test_web_app.py -q` → 모두 통과
- [ ] **Step 5: 실제 데이터 확인** — OpenTyrian 작업에 대해 `diagnosis.load`와 `tangle`을 실행해 headline·cycle_size(43)·leverage(opentyr 20)·links(333)를 확인하고, 수정본(4de3…)과 비교한 엉킴 총량이 100보다 약간 작은지 확인한다.

커밋: 이 프로젝트는 사용자가 요청할 때만 커밋한다. 단계 끝에 변경 파일 목록만 보고한다.


## 실행 중 수정 (2026-10-19)

- 실제 OpenTyrian 확인에서 문장에 '단위'가 그대로 노출되어 `_sentence(unit, cycle_size, label)`로 바꾸고 '다른 파일 …곳', 'N개 파일이 얽힌'처럼 언어별 단위명을 쓰게 했다.
- 10월 19일 수정의 작은 개선(초과 복잡도 3,325 → 3,317)이 반올림으로 100.0에 묻혀 엉킴 총량을 소수점 둘째 자리로 계산한다.
