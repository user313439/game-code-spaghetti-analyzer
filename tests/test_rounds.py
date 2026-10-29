"""Rounds: each applied change builds on the previous revision; undo and play confirmation are recorded."""
import json
import time

import pytest

pytest.importorskip('fastapi')
from fastapi.testclient import TestClient

from game_si.web import assistant
from game_si.web.app import create_app


def provider(service, mode, prompt, model='', api_key='', **kw):
    old, new = ('return 1;', 'return 2;') if 'return 1;' in prompt else ('return 0;', 'return 1;')
    return dict(reasons=['근거입니다.'], suggestions=['방향입니다.'], tests=['확인합니다.'], uncertainty='', relationships=[],
                file_reviews=[dict(path='main.c', role='역할입니다.', finding='문제입니다.', reason='이유입니다.', change='바꿉니다.',
                                   expected_effect='좋아집니다.', impact='영향입니다.', decision='refactor', change_type='functions',
                                   targets=['Tick'], evidence=['Tick 함수'], checks=['설정 화면 | 음량 막대 조절하기', '반환값 확인'])],
                companions=[], creates=[], edits=[dict(path='main.c', old=old, new=new)])


def wait(client, url):
    for _ in range(600):
        state = client.get(url).json()
        if state['state'] != 'running':
            return state
        time.sleep(0.05)
    raise AssertionError('task did not finish')


def test_rounds_stack_undo_and_play_confirmation(tmp_path, monkeypatch):
    monkeypatch.setattr(assistant, 'call_provider', provider)
    app = create_app(tmp_path)
    manager = app.state.manager
    job = manager.create('라운드 게임', 'folder')
    ident = job['id']
    (manager.directory(ident) / 'input' / 'main.c').write_text('int Tick(void) { return 0; }\n', encoding='utf8')
    result = manager.directory(ident) / 'result'
    result.mkdir()
    (result / 'scoring.json').write_text(json.dumps({'class_scores': [{'fqn': 'main', 'name': 'main', 'file_path': 'main.c', 'si': 100,
        'grade': 'E', 'loc': 1, 'raw': {'cc': 1, 'coupling': 0, 'dependency_cycle': 0, 'global_state': 0, 'game_loop_centrality': 0}}],
        'analysis_status': {'state': 'complete', 'language': 'c'}}), encoding='utf8')
    (result / 'metrics.json').write_text(json.dumps({'classes': [{'fqn': 'main', 'name': 'main', 'file_path': 'main.c', 'out_neighbors': [], 'in_neighbors': []}],
        'methods': [dict(file_path='main.c', class_fqn='main', name='Tick', fqn='main.Tick', start_line=1, end_line=1, cc=1, loc=1)]}), encoding='utf8')
    manager.update(ident, state='complete', options={'lang': 'c', 'subdir': '.'})
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        h = {'X-Game-SI-Token': client.get('/api/session').json()['token']}
        url = f'/api/jobs/{ident}/assistant'

        def change():
            candidate = client.get(url + '/candidates').json()[0]['fqn']
            assert client.post(url, headers=h, json=dict(action='preview', service='codex', mode='cli', candidates=[candidate], direct=True)).status_code == 202
            state = wait(client, url)
            assert state['state'] == 'complete', state.get('error')
            assert client.post(url + '/apply', headers=h, json={'preview_id': state['preview_id']}).status_code == 202
            state = wait(client, url)
            assert state['state'] == 'complete', state.get('error')
            return state

        first = change()
        second = change()
        rounds = client.get(f'/api/jobs/{ident}/rounds').json()
        assert rounds['current'] == 2 and [r['base'] for r in rounds['rounds']] == [None, first['revision']]
        copy = manager.directory(ident) / 'revisions' / second['revision'] / 'source' / 'main.c'
        assert 'return 2;' in copy.read_text('utf8')
        assert (manager.directory(ident) / 'input' / 'main.c').read_text('utf8') == 'int Tick(void) { return 0; }\n'
        assert rounds['rounds'][1]['checks']['original_preserved'] is True and rounds['rounds'][1]['comparison']
        tangle = client.get(f'/api/jobs/{ident}/tangle').json()
        assert [r['round'] for r in tangle['rounds']] == [0, 1, 2] and tangle['current'] == 2
        assert client.get(f'/api/jobs/{ident}/diagnosis').json()['round'] == 2
        assert client.post(f'/api/jobs/{ident}/rounds/2/play', json={'ok': True}).status_code == 403
        played = client.post(f'/api/jobs/{ident}/rounds/2/play', headers=h, json={'ok': True, 'note': '이동·발사 정상'}).json()
        assert played['rounds'][1]['checks']['play']['ok'] is True
        assert client.post(f'/api/jobs/{ident}/rounds/9/play', headers=h, json={'ok': True}).status_code == 404
        # Each round keeps how it changed the code and what to try in the game, place first.
        assert rounds['rounds'][1]['method'] == 'functions'
        assert rounds['rounds'][1]['play_checks'] == [
            {'where': '설정 화면', 'action': '음량 막대 조절하기', 'file': 'main.c', 'targets': ['Tick']},
            {'where': '', 'action': '반환값 확인', 'file': 'main.c', 'targets': ['Tick']}]
        # A problem report with a screenshot is kept next to its round; only real images are accepted.
        png = b'\x89PNG\r\n\x1a\n' + b'0' * 20
        form = {'kind': '조작이 안 돼요', 'where': '설정 화면 · 음량 막대 조절하기', 'note': '두 칸씩 움직여요', 'checked': json.dumps(['설정 화면: 음량 막대 조절하기'])}
        report = f'/api/jobs/{ident}/rounds/2/report'
        assert client.post(report, headers=h, data=dict(form, kind='모름')).status_code == 400
        assert client.post(report, headers=h, data=form, files={'screenshot': ('a.png', b'GIF89a', 'image/png')}).status_code == 400
        reported = client.post(report, headers=h, data=form, files={'screenshot': ('a.png', png, 'image/png')}).json()
        play = reported['rounds'][1]['checks']['play']
        assert play['ok'] is False and play['kind'] == '조작이 안 돼요' and play['note'] == '두 칸씩 움직여요'
        assert (manager.directory(ident) / 'revisions' / second['revision'] / 'reports' / play['screenshot']).read_bytes() == png
        undone = client.post(f'/api/jobs/{ident}/rounds/undo', headers=h).json()
        assert undone['current'] == 1
        assert client.get(f'/api/jobs/{ident}/diagnosis').json()['revision'] == first['revision']
        third = change()   # replaces the undone second round
        rounds = client.get(f'/api/jobs/{ident}/rounds').json()
        assert rounds['current'] == 2 and rounds['rounds'][1]['revision'] == third['revision'] and len(rounds['rounds']) == 2
        assert 'next_pending' not in client.get(url).json()          # cleared once the next prescription was asked for (or not)
        # Up to 3 stages × 24 checks can be ticked (the page sends each cut to 200 characters).
        many = [f'화면 {i}: ' + '가' * 190 for i in range(72)]
        assert client.post(f'/api/jobs/{ident}/rounds/2/play', headers=h, json={'ok': True, 'checked': many}).status_code == 200
        # A screenshot larger than allowed is refused before the form is read.
        big = {'screenshot': ('a.png', b'0' * (7 * 1024 * 1024), 'image/png')}
        assert client.post(f'/api/jobs/{ident}/rounds/2/report', headers=h, data={'kind': '기타'}, files=big).status_code == 400
        # No fourth stage, whichever page the change is asked from.
        path = manager.directory(ident) / 'rounds.json'
        data = json.loads(path.read_text('utf8'))
        data['rounds'].append(dict(data['rounds'][1], round=3))
        data['current'] = 3
        path.write_text(json.dumps(data), encoding='utf8')
        candidate = client.get(url + '/candidates').json()[0]['fqn']
        refused = client.post(url, headers=h, json=dict(action='preview', service='codex', mode='cli', candidates=[candidate], direct=True))
        assert refused.status_code == 400 and '최대 3단계' in refused.json()['detail']
