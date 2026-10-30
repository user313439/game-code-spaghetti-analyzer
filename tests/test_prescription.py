import json
import time

import pytest

from game_si.web import diagnosis, prescription
from web_redesign_sample import sample


def diag():
    return diagnosis.build(*sample())


def good(**over):
    data = {'done': False, 'files': [
        {'name': 'b', 'kind': 'link', 'reason': '여러 파일이 이 파일을 부릅니다.', 'change_idea': '공용 부분을 따로 둡니다.', 'expected': '고리가 줄어듭니다.'},
        {'name': 'a', 'kind': 'internal', 'reason': '함수가 깁니다.', 'change_idea': '함수를 나눕니다.', 'expected': '읽기 쉬워집니다.'}],
        'why_not_top': '', 'benefit': '고칠 때 영향이 덜 퍼집니다.'}
    data.update(over)
    return data


def test_context_lists_units_and_header_excerpts(tmp_path):
    (tmp_path / 'a.c').write_text('int big(void){return 1;}')
    (tmp_path / 'a.h').write_text('/* license\n long text */\ntypedef int JE_byte;\nint big(void);\n')
    text, meta = prescription.build_context(diag(), tmp_path)
    payload = json.loads(text)
    assert [u['name'] for u in payload['units']][:2] == ['a', 'b'] and payload['project']['cycle_size'] == 3
    excerpt = next(e for e in payload['excerpts'] if e['name'] == 'a')
    assert excerpt['path'] == 'a.h' and 'typedef int JE_byte;' in excerpt['text'] and 'license' not in excerpt['text']
    assert meta['bytes'] == len(text.encode('utf8')) <= prescription.MAX_CONTEXT_BYTES


def test_validate_accepts_good_and_rejects_bad_answers():
    names = {'a', 'b', 'c', 'd'}
    assert prescription.validate(good(), names)['files'][0]['name'] == 'b'
    assert prescription.validate(good(done=True, files=[], benefit=''), names)['done'] is True
    bad = [good(files=[dict(good()['files'][0], name='zzz')]),
           good(files=[dict(good()['files'][0], name=n) for n in 'abcdab']),
           good(files=[dict(good()['files'][0], kind='other')]),
           good(files=[dict(good()['files'][0], reason='긴 문장입니다.' * 60)]),
           good(files=[dict(good()['files'][0], reason='여러 파일이 부른다.')]),
           good(files=[good()['files'][0], good()['files'][0]]),
           good(files=[]),
           good(benefit='')]
    for data in bad:
        with pytest.raises(ValueError):
            prescription.validate(data, names)


def test_effects_are_computed_by_program_with_warning():
    g = diag()['graph']
    eff = prescription.effects([{'name': 'b', 'kind': 'link'}, {'name': 'a', 'kind': 'internal'}, {'name': 'd', 'kind': 'link'}], g)
    assert eff['base'] == 3 and eff['final'] == 0
    assert [(s['name'], s['after'], s['reduced']) for s in eff['steps']] == [('b', 0, True), ('a', None, False), ('d', 0, False)]


def test_headline_depends_on_computed_result():
    g = diag()['graph']
    files = [{'name': 'b', 'kind': 'link'}]
    assert prescription.headline(files, prescription.effects(files, g), '파일', False) == '1개 파일만 정리해도 순환 고리가 크게 풀립니다.'
    inner = [{'name': 'a', 'kind': 'internal'}]
    assert prescription.headline(inner, prescription.effects(inner, g), '파일', False) == '이 파일의 복잡한 함수부터 정리합니다.'
    assert prescription.headline([], {'base': 3, 'final': 3, 'steps': []}, '파일', True) == '지금 기준으로는 효과가 큰 처방이 없습니다.'


class FakeJobs:
    def __init__(self, root):
        self.root = root
        self.lock = __import__('threading').RLock()
        (root / 'result').mkdir(parents=True)
        m, s = sample()
        (root / 'result/metrics.json').write_text(json.dumps(m))
        (root / 'result/scoring.json').write_text(json.dumps(s))
        (root / 'input').mkdir()

    def folder(self, ident):
        return self.root

    def source(self, ident):
        return self.root / 'input'

    def get(self, ident):
        return {'state': 'idle'}


def wait(service, ident):
    for _ in range(100):
        state = service.get(ident)
        if state['state'] != 'running':
            return state
        time.sleep(0.05)
    raise AssertionError('prescription did not finish')


def test_service_retries_once_then_saves_result(tmp_path, monkeypatch):
    replies = [good(files=[dict(good()['files'][0], name='zzz')]), good()]
    prompts = []

    def fake(service, mode, prompt, model='', api_key='', **kw):
        prompts.append(prompt)
        return replies.pop(0)
    monkeypatch.setattr(prescription.assistant, 'call_provider', fake)
    service = prescription.Prescriptions(FakeJobs(tmp_path))
    ident = 'f' * 32
    assert service.get(ident)['state'] == 'idle'
    service.start(ident, {'service': 'claude', 'mode': 'cli'})
    state = wait(service, ident)
    assert state['state'] == 'complete' and len(prompts) == 2 and '이전 응답' in prompts[1]
    result = state['result']
    assert result['headline'] == '2개 파일만 정리해도 순환 고리가 크게 풀립니다.'
    assert result['effects']['steps'][0]['after'] == 0 and result['service'] == 'claude'
    assert state['stale'] is False and (tmp_path / 'prescription.json').is_file()
    # analysis changed → stored prescription is marked stale, not silently reused
    s = json.loads((tmp_path / 'result/scoring.json').read_text())
    s['class_scores'][0]['si'] = 99.0
    (tmp_path / 'result/scoring.json').write_text(json.dumps(s))
    fresh = prescription.Prescriptions(service.jobs)
    assert fresh.get(ident)['stale'] is True


def test_service_fails_after_second_bad_answer(tmp_path, monkeypatch):
    monkeypatch.setattr(prescription.assistant, 'call_provider', lambda *a, **k: good(files=[]))
    service = prescription.Prescriptions(FakeJobs(tmp_path))
    service.start('e' * 32, {'service': 'codex', 'mode': 'cli'})
    state = wait(service, 'e' * 32)
    assert state['state'] == 'failed' and '처방' in state['error'] and 'result' not in state


def test_service_rejects_bad_connection(tmp_path):
    service = prescription.Prescriptions(FakeJobs(tmp_path))
    with pytest.raises(ValueError):
        service.start('d' * 32, {'service': 'nope', 'mode': 'cli'})
    with pytest.raises(ValueError):
        service.start('d' * 32, {'service': 'claude', 'mode': 'api'})


def test_prescription_api_requires_token_and_runs(tmp_path, monkeypatch):
    pytest.importorskip('fastapi')
    from fastapi.testclient import TestClient
    from game_si.web.app import create_app
    monkeypatch.setattr(prescription.assistant, 'call_provider', lambda *a, **k: good())
    with TestClient(create_app(tmp_path), base_url='http://127.0.0.1:8765') as client:
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
        url = f"/api/jobs/{job['id']}/prescription"
        assert client.get(url).status_code == 409              # analysis not finished yet (same as /diagnosis)
        manager.update(job['id'], state='complete')
        assert client.get(url).json()['state'] == 'idle'
        assert client.post(url, json={'service': 'claude', 'mode': 'cli'}).status_code == 403
        assert client.post(url, headers=h, json={'service': 'claude', 'mode': 'cli'}).status_code == 202
        for _ in range(100):
            state = client.get(url).json()
            if state['state'] != 'running':
                break
            time.sleep(0.05)
        assert state['state'] == 'complete' and state['result']['files'][0]['name'] == 'b'
        assert 'api_key' not in json.dumps(state)


def test_validate_keeps_which_way_first_only_when_both_kinds_are_offered():
    names = {'a', 'b', 'c', 'd'}
    both = prescription.validate(good(first='link', first_reason='고리를 먼저 풀면 나머지가 쉬워집니다.'), names)
    assert both['first'] == 'link' and both['first_reason'].startswith('고리')
    assert prescription.validate(good(), names)['first'] == 'internal'          # no pick: split functions first
    one = prescription.validate(good(files=[good()['files'][1]], first='link', first_reason='이유입니다.'), names)
    assert one['first'] == '' and one['first_reason'] == ''
    with pytest.raises(ValueError):
        prescription.validate(good(first='internal', first_reason='먼저 한다.'), names)


def test_precise_analysis_never_offers_moving_declarations():
    data = prescription.validate(good(), {'a', 'b'})
    assert prescription.drop_unmeasurable(data, 'tree-sitter') is data
    kept = prescription.drop_unmeasurable(data, 'clang')
    assert [f['name'] for f in kept['files']] == ['a'] and kept['dropped_links'] == 1 and kept['done'] is False
    only = prescription.drop_unmeasurable(prescription.validate(good(files=[good()['files'][0]]), {'a', 'b'}), 'clang')
    assert only['done'] is True and only['files'] == [] and only['benefit'] == ''


def test_files_whose_targets_cannot_be_read_as_measured_are_not_offered(tmp_path):
    # video_scale_hqNx.c: the analysis measures hq4x_32 over thousands of lines; the change checks read it
    # short or not at all (macros), so a change there could never be checked.
    src = tmp_path / 'src'
    src.mkdir()
    (src / 'game.c').write_text('static int small(int x)\n{\n    if (x) return 1;\n    return 0;\n}\n', encoding='utf8')
    (src / 'scale.c').write_text('void hq2x(int x)\n{\n    if (x) x++;\n}\n', encoding='utf8')
    (src / 'Menu.cs').write_text('class Menu { void Draw() { } }\n', encoding='utf8')
    units = {'g': {'file': 'src/game.c'}, 's': {'file': 'src/scale.c'}, 'm': {'file': 'src/Menu.cs'}}
    methods = [{'file_path': 'src/game.c', 'name': 'small', 'start_line': 1, 'end_line': 5},
               {'file_path': 'src/scale.c', 'name': 'hq2x', 'start_line': 1, 'end_line': 900},   # read short
               {'file_path': 'src/scale.c', 'name': 'hq4x', 'start_line': 950, 'end_line': 3000}]   # not read at all
    item = lambda name, targets, kind='internal': {'name': name, 'kind': kind, 'reason': '이유', 'change_idea': '나눕니다',
                                                   'expected': '', 'targets': targets}
    data = {'done': False, 'why_not_top': '', 'benefit': '찾기 쉬워집니다.', 'first': '', 'first_reason': '',
            'files': [item('g', ['small', 'unknown']), item('s', ['hq2x']), item('m', ['Draw'])]}
    kept = prescription.drop_unreadable(data, units, methods, tmp_path)
    assert [f['name'] for f in kept['files']] == ['g', 'm'] and kept['dropped_unreadable'] == ['s'] and kept['done'] is False
    assert prescription.drop_unreadable(dict(data, files=[item('s', ['hq4x'])]), units, methods, tmp_path)['done'] is True
    # Moving declarations and a file the analysis read the same way stay; nothing to drop leaves the answer as it was.
    same = dict(data, files=[item('g', ['small']), item('s', [], 'link')])
    assert prescription.drop_unreadable(same, units, methods, tmp_path) is same
    assert prescription.drop_unreadable(data, units, methods, None) is data


class RoundJobs(FakeJobs):
    current = 0

    def rounds(self, ident):
        return {'rounds': [{'round': n + 1, 'files': ['a.c']} for n in range(self.current)], 'current': self.current}


def test_stages_stop_at_three_and_the_next_one_is_asked_for_by_itself(tmp_path, monkeypatch):
    prompts = []
    monkeypatch.setattr(prescription.assistant, 'call_provider', lambda s, m, prompt, *a, **k: prompts.append(prompt) or good())
    jobs = RoundJobs(tmp_path)
    service = prescription.Prescriptions(jobs)
    ident = 'c' * 32
    assert service.auto_next(ident) is None                         # nothing asked before: no connection to reuse
    service.start(ident, {'service': 'codex', 'mode': 'cli', 'model': 'gpt-6.1-sol'})
    assert wait(service, ident)['result']['stage'] == 1
    jobs.current = 1
    assert service.auto_next(ident)['auto'] is True
    state = wait(service, ident)
    assert state['result']['stage'] == 2 and state['model'] == 'gpt-6.1-sol' and '"stage": 2' in prompts[-1]
    jobs.current = 3
    assert service.auto_next(ident) is None
    with pytest.raises(ValueError, match='최대 3단계'):
        service.start(ident, {'service': 'codex', 'mode': 'cli'})
    service.states[ident]['mode'] = 'api'                          # a key is never kept, so no automatic request
    jobs.current = 1
    assert service.auto_next(ident) is None
