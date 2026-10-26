import json

import pytest

from game_si.web import diagnosis
from web_redesign_sample import sample


def test_units_have_percentiles_neighbors_cycle_and_functions():
    d = diagnosis.build(*sample())
    a = next(u for u in d['units'] if u['name'] == 'a')
    assert [u['name'] for u in d['units']] == ['a', 'b', 'c', 'd']
    assert a['calls'] == ['b'] and set(a['called_by']) == {'c', 'd'}
    assert a['in_cycle'] is True and a['functions'][0] == {'name': 'big', 'cc': 30, 'loc': 90, 'line': 3}
    assert a['function_count'] == 2 and a['pct']['cc'] == 100 and a['top']['cc'] == 25
    assert a['pct']['global_state'] == 0 and a['pct']['game_loop_centrality'] == 0
    assert next(u for u in d['units'] if u['name'] == 'd')['in_cycle'] is False
    # Rank per measure: 1 + units with a larger value; equal values share it.
    assert a['rank']['cc'] == 1 and a['tied']['cc'] is False
    zero = {u['rank']['global_state'] for u in d['units'] if not u['raw']['global_state']}
    assert len(zero) <= 1 and all(u['tied']['global_state'] for u in d['units'] if not u['raw']['global_state']) == (len([u for u in d['units'] if not u['raw']['global_state']]) > 1)


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
    assert a['sentence'] == '가장 복잡한 함수 big의 복잡도(CC)가 30입니다. 다른 파일 1곳을 부르고 2곳에서 불립니다.'
    assert {n['id'] for n in d['graph']['nodes']} == set('abcd') and len(d['graph']['edges']) == 4


def test_several_cycles_are_all_counted_like_the_result_page():
    # Rehearsal 2026-10-26: three separate two-file cycles were told as "2 files in one cycle" while the
    # result page counted the 6 files in any cycle.
    m, s = sample(cut=True)
    out = {'a': ['b'], 'b': ['a'], 'c': ['d'], 'd': ['c', 'a']}   # two separate two-file cycles: a<->b, c<->d
    for cls in m['classes']:
        cls['out_neighbors'] = out[cls['fqn']]
    d = diagnosis.build(m, s)
    assert d['summary']['cycles'] == 2 and d['summary']['cycle_units'] == 4 and d['summary']['cycle_size'] == 2
    assert d['headline'].endswith('4개 파일이 순환 고리 2개로 묶여 있습니다.')
    assert {u['name']: u['cycle_size'] for u in d['units']} == {'a': 2, 'b': 2, 'c': 2, 'd': 2}
    assert d['units'][0]['tie_count']['dependency_cycle'] == 3   # a, b, c share the cycle measure in the sample


def test_class_language_uses_class_label_and_no_cycle_headline():
    m, s = sample(cut=True)
    s['analysis_status']['language'] = 'csharp'
    d = diagnosis.build(m, s)
    assert d['summary']['unit_label'] == '클래스'
    assert d['headline'] == '4개 클래스 중 1개가 심하게 엉켜 있고, 순환 고리는 없습니다.'


def test_load_caches_by_scoring_fingerprint(tmp_path):
    m, s = sample()
    (tmp_path / 'metrics.json').write_text(json.dumps(m))
    (tmp_path / 'scoring.json').write_text(json.dumps(s))
    first = diagnosis.load(tmp_path)
    assert (tmp_path / 'diagnosis.json').is_file() and diagnosis.load(tmp_path) == first
    s['class_scores'][0]['si'] = 99.0
    (tmp_path / 'scoring.json').write_text(json.dumps(s))
    assert diagnosis.load(tmp_path)['units'][0]['si'] == 99.0


def test_diagnosis_and_tangle_api(tmp_path):
    pytest.importorskip('fastapi')
    from fastapi.testclient import TestClient
    from game_si.web.app import create_app
    app = create_app(tmp_path)
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        token = client.get('/api/session').json()['token']
        h = {'X-Game-SI-Token': token, 'Origin': 'http://127.0.0.1:8765'}
        job = client.post('/api/import/files', headers=h, data={'paths': json.dumps(['a.c']), 'name': 't'},
                          files=[('files', ('a.c', b'int f(){return 1;}', 'application/octet-stream'))]).json()
        manager = client.app.state.manager
        result = manager.directory(job['id']) / 'result'
        result.mkdir()
        m, s = sample()
        (result / 'metrics.json').write_text(json.dumps(m))
        (result / 'scoring.json').write_text(json.dumps(s))
        assert client.get(f"/api/jobs/{job['id']}/diagnosis").status_code == 409
        manager.update(job['id'], state='complete')
        d = client.get(f"/api/jobs/{job['id']}/diagnosis").json()
        assert d['summary']['cycle_size'] == 3 and 'fingerprint' in d
        t = client.get(f"/api/jobs/{job['id']}/tangle").json()
        first = t['rounds'][0]
        assert first['round'] == 0 and first['revision'] is None and first['index'] == 100.0 and first['same_units']
        assert client.get(f"/api/jobs/{job['id']}/diagnosis?revision={'0' * 32}").status_code == 404
        assert client.get(f"/api/jobs/{job['id']}/diagnosis?revision=../x").status_code == 400
